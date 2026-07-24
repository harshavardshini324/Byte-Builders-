#!/usr/bin/env python3
"""
doc_generator.py - Automated Python Docstring Injector using AST and Google GenAI SDK.
"""

import argparse
import ast
import os
import sys
from typing import Dict, List, Optional

try:
    from google import genai
    from google.genai.errors import APIError

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


STYLE_PROMPTS = {
    "google": (
        "Google style docstring format:\n"
        "Short summary.\n\n"
        "Args:\n"
        "    param_name (type): Description.\n\n"
        "Returns:\n"
        "    return_type: Description."
    ),
    "sphinx": (
        "Sphinx reStructuredText style docstring format:\n"
        "Short summary.\n\n"
        ":param param_name: Description.\n"
        ":type param_name: type\n"
        ":returns: Description.\n"
        ":rtype: return_type"
    ),
    "numpy": (
        "NumPy style docstring format:\n"
        "Short summary.\n\n"
        "Parameters\n"
        "----------\n"
        "param_name : type\n"
        "    Description.\n\n"
        "Returns\n"
        "-------\n"
        "return_type\n"
        "    Description."
    ),
}


def clean_docstring_response(response_text: str) -> str:
  """Clean markdown formatting and surrounding quotes from LLM response."""
  text = response_text.strip()

  # Strip markdown block if enclosed in ```
  if text.startswith("```"):
    lines = text.splitlines()
    if lines[0].startswith("```"):
      lines = lines[1:]
    if lines and lines[-1].startswith("```"):
      lines = lines[:-1]
    text = "\n".join(lines).strip()

  # Strip surrounding triple quotes if model returned them
  if (text.startswith('"""') and text.endswith('"""')) or (
      text.startswith("'''") and text.endswith("'''")
  ):
    text = text[3:-3].strip()
  elif (text.startswith('"') and text.endswith('"')) or (
      text.startswith("'") and text.endswith("'")
  ):
    text = text[1:-1].strip()

  return text


class RepoAnalyzer:
  """Scans repository directory, builds cross-module dependency graph and symbol map."""

  def __init__(self, repo_dir: str):
    self.repo_dir = os.path.abspath(repo_dir)
    self.modules: Dict[str, ast.Module] = {}  # rel_path -> AST Module
    self.symbols: Dict[str, List[str]] = (
        {}
    )  # symbol_name -> list of rel_paths defining it
    self.imports: Dict[str, List[str]] = (
        {}
    )  # rel_path -> list of imported module/symbol names
    self._scan_repo()

  def _scan_repo(self):
    ignore_dirs = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
    }
    for root, dirs, files in os.walk(self.repo_dir):
      dirs[:] = [d for d in dirs if d not in ignore_dirs]
      for file in files:
        if file.endswith(".py"):
          full_path = os.path.join(root, file)
          rel_path = os.path.relpath(full_path, self.repo_dir).replace("\\", "/")
          try:
            with open(full_path, "r", encoding="utf-8") as f:
              code = f.read()
            tree = ast.parse(code, filename=full_path)
            self.modules[rel_path] = tree
            self._extract_symbols_and_imports(rel_path, tree)
          except Exception:
            pass

  def _extract_symbols_and_imports(self, rel_path: str, tree: ast.Module):
    self.imports[rel_path] = []
    for node in ast.walk(tree):
      if isinstance(
          node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
      ):
        self.symbols.setdefault(node.name, []).append(rel_path)
      elif isinstance(node, ast.Import):
        for alias in node.names:
          self.imports[rel_path].append(alias.name)
      elif isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        for alias in node.names:
          self.imports[rel_path].append(
              f"{mod}.{alias.name}" if mod else alias.name
          )

  def get_symbol_context(self, rel_path: str, symbol_name: str) -> str:
    """Builds cross-module context string for LLM prompt."""
    imported = self.imports.get(rel_path, [])
    referencing_modules = []
    for other_path, imp_list in self.imports.items():
      if other_path != rel_path:
        if any(symbol_name in item for item in imp_list):
          referencing_modules.append(other_path)

    context_parts = [f"Repository File: {rel_path}"]
    if imported:
      context_parts.append(f"Imports: {', '.join(imported[:5])}")
    if referencing_modules:
      context_parts.append(f"Referenced By: {', '.join(referencing_modules[:5])}")

    return " | ".join(context_parts)


class DocstringGenerator:
  """Communicates with Google GenAI SDK to generate docstrings."""

  def __init__(
      self,
      model_name: str = "gemini-2.5-flash",
      api_key: Optional[str] = None,
      dry_run: bool = False,
  ):
    self.dry_run = dry_run
    self.model_name = model_name

    if not self.dry_run:
      if not GENAI_AVAILABLE:
        raise ImportError(
            "The 'google-genai' package is not installed. "
            "Please install it using: pip install google-genai"
        )

      # Initialize GenAI Client
      kwargs = {}
      if api_key:
        kwargs["api_key"] = api_key
      self.client = genai.Client(**kwargs)

  def generate_docstring(
      self,
      name: str,
      code: str,
      style: str,
      node_type: str = "function",
      repo_context: Optional[str] = None,
  ) -> str:
    """Requests Gemini API (or generates mock) to produce docstring with cross-module context."""
    if self.dry_run:
      ctx_prefix = f" [{repo_context}]" if repo_context else ""
      if node_type == "module":
        return (
            f"Auto-generated module docstring.{ctx_prefix}\n\nProvides data"
            " processing, user filtering, and cross-module utilities."
        )
      elif node_type == "class":
        if style == "google":
          return (
              f"Auto-generated Google docstring for class {name}.{ctx_prefix}\n\nAttributes:\n    name"
              " (str): The name identifier for the instance."
          )
        elif style == "sphinx":
          return (
              f"Auto-generated Sphinx docstring for class {name}.{ctx_prefix}\n\n:ivar"
              " name: The name identifier for the instance."
          )
        elif style == "numpy":
          return (
              f"Auto-generated NumPy docstring for class {name}.{ctx_prefix}\n\nAttributes\n----------\nname"
              " : str\n    The name identifier for the instance."
          )

      if style == "google":
        return (
            f"Auto-generated Google docstring for {name}.{ctx_prefix}\n\nArgs:\n    *args:"
            " Function arguments.\n\nReturns:\n    Any: Function result."
        )
      elif style == "sphinx":
        return (
            f"Auto-generated Sphinx docstring for {name}.{ctx_prefix}\n\n:param"
            " args: Function arguments.\n:returns: Function result.\n:rtype: Any"
        )
      elif style == "numpy":
        return (
            f"Auto-generated NumPy docstring for {name}.{ctx_prefix}\n\nParameters\n----------\nargs\n    Function"
            " arguments.\n\nReturns\n-------\nAny\n    Function result."
        )

    style_guide = STYLE_PROMPTS.get(style.lower(), STYLE_PROMPTS["google"])
    ctx_section = (
        f"Cross-Module Architectural Context:\n{repo_context}\n\n"
        if repo_context
        else ""
    )

    prompt = (
        f"You are a professional Python documentation assistant.\nGenerate ONLY"
        f" a python docstring for the following {node_type}.\n{ctx_section}Follow"
        f" the {style.upper()} docstring convention exact"
        f" structure:\n{style_guide}\n\nRULES:\n1. DO NOT include code or"
        " function signatures.\n2. DO NOT wrap the output in triple backticks"
        " (```) or code blocks.\n3. DO NOT include triple quotes ("
        '"""'
        ") in your response; return raw text only.\n4. Be accurate with types,"
        f" parameter names, and return values.\n\n{node_type.capitalize()} Source"
        f" Code Snippet:\n```python\n{code}\n```"
    )

    model_candidates = [self.model_name]
    if self.model_name == "gemini-2.5-flash":
      model_candidates.extend(["gemini-2.0-flash", "gemini-1.5-flash"])

    last_error = None
    for model in model_candidates:
      try:
        response = self.client.models.generate_content(
            model=model, contents=prompt
        )
        if response and response.text:
          return clean_docstring_response(response.text)
      except Exception as e:
        last_error = e
        err_str = str(e)
        # Retry with fallback model if model not found (404)
        if "404" in err_str or "NOT_FOUND" in err_str:
          continue
        elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
          print(
              "\n[Quota Exceeded (429)]: Gemini API rate limit reached for"
              f" key/model '{model}'.\nTip: You can use '--dry-run' to test AST"
              " injection offline without API quota limits.",
              file=sys.stderr,
          )
          raise e
        else:
          raise e

    print(
        f"[Error generating docstring for '{name}']: {last_error}",
        file=sys.stderr,
    )
    raise last_error


class DocstringInjector(ast.NodeTransformer):
  """AST NodeTransformer that identifies undocumented modules, classes, and functions and injects docstrings."""

  def __init__(
      self,
      generator: DocstringGenerator,
      style: str = "google",
      rel_path: str = "",
      repo_analyzer: Optional[RepoAnalyzer] = None,
  ):
    super().__init__()
    self.generator = generator
    self.style = style
    self.rel_path = rel_path
    self.repo_analyzer = repo_analyzer
    self.injected_count = 0

  def _get_context(self, symbol_name: str) -> Optional[str]:
    if self.repo_analyzer and self.rel_path:
      return self.repo_analyzer.get_symbol_context(self.rel_path, symbol_name)
    return None

  def visit_Module(self, node: ast.Module) -> ast.AST:
    existing_doc = ast.get_docstring(node)
    if not existing_doc:
      print(f"[Injecting] Generating '{self.style}' module-level docstring...")
      module_code = ast.unparse(node)[:1000]
      repo_ctx = self._get_context("Module")
      docstring_text = self.generator.generate_docstring(
          "Module",
          module_code,
          self.style,
          node_type="module",
          repo_context=repo_ctx,
      )
      doc_node = ast.Expr(value=ast.Constant(value=docstring_text))
      node.body.insert(0, doc_node)
      self.injected_count += 1
    else:
      print("[Skip] Module already has a docstring.")
    return self.generic_visit(node)

  def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
    existing_doc = ast.get_docstring(node)
    if not existing_doc:
      print(
          f"[Injecting] Generating '{self.style}' docstring for class"
          f" '{node.name}'..."
      )
      class_code = ast.unparse(node)
      repo_ctx = self._get_context(node.name)
      docstring_text = self.generator.generate_docstring(
          node.name,
          class_code,
          self.style,
          node_type="class",
          repo_context=repo_ctx,
      )
      doc_node = ast.Expr(value=ast.Constant(value=docstring_text))
      node.body.insert(0, doc_node)
      self.injected_count += 1
    else:
      print(f"[Skip] Class '{node.name}' already has a docstring.")
    return self.generic_visit(node)

  def _process_function(self, node: ast.AST) -> ast.AST:
    # Check if function already has a docstring
    existing_doc = ast.get_docstring(node)
    if existing_doc:
      print(f"[Skip] Function '{node.name}' already has a docstring.")
      return self.generic_visit(node)

    print(
        f"[Injecting] Generating '{self.style}' docstring for function"
        f" '{node.name}'..."
    )

    # Get unparsed code for function node
    func_code = ast.unparse(node)
    repo_ctx = self._get_context(node.name)

    # Generate docstring
    docstring_text = self.generator.generate_docstring(
        node.name,
        func_code,
        self.style,
        node_type="function",
        repo_context=repo_ctx,
    )

    # Create ast.Expr containing ast.Constant with the docstring text
    doc_node = ast.Expr(value=ast.Constant(value=docstring_text))

    # Insert docstring as the first statement in function body
    node.body.insert(0, doc_node)
    self.injected_count += 1

    return self.generic_visit(node)

  def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
    return self._process_function(node)

  def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
    return self._process_function(node)


def audit_file(file_path: str, min_coverage: float = 80.0) -> bool:
  """Scans target Python file, computes docstring coverage, and enforces minimum coverage threshold."""
  if not os.path.exists(file_path):
    raise FileNotFoundError(f"Source file not found: {file_path}")

  with open(file_path, "r", encoding="utf-8") as f:
    source_code = f.read()

  tree = ast.parse(source_code, filename=file_path)

  total_nodes = 0
  documented_nodes = 0
  missing_items = []

  # Evaluate Module level
  total_nodes += 1
  if ast.get_docstring(tree):
    documented_nodes += 1
  else:
    missing_items.append("Module Header")

  # Walk AST nodes
  for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
      total_nodes += 1
      if ast.get_docstring(node):
        documented_nodes += 1
      else:
        missing_items.append(f"Class '{node.name}'")

    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
      total_nodes += 1
      if ast.get_docstring(node):
        documented_nodes += 1
      else:
        missing_items.append(f"Function '{node.name}'")

  coverage = (documented_nodes / total_nodes * 100.0) if total_nodes > 0 else 100.0
  passed = coverage >= min_coverage

  print("\n" + "=" * 50)
  print(" DOCUMENTATION COVERAGE AUDIT REPORT")
  print("=" * 50)
  print(f" Target File       : {file_path}")
  print(f" Total Evaluated   : {total_nodes} item(s)")
  print(f" Documented        : {documented_nodes} item(s)")
  print(f" Missing           : {len(missing_items)} item(s)")
  print(f" Coverage Score    : {coverage:.2f}%")
  print(f" Required Threshold: {min_coverage:.2f}%")
  print("=" * 50)

  if missing_items:
    print("\nUndocumented Items:")
    for item in missing_items:
      print(f"  [MISSING] {item}")

  if passed:
    print(
        f"\n[PASS] Coverage score {coverage:.2f}% meets required threshold"
        f" ({min_coverage:.2f}%).\n"
    )
  else:
    print(
        f"\n[FAIL] Coverage score {coverage:.2f}% is below required"
        f" threshold ({min_coverage:.2f}%).\n"
    )

  return passed


def process_file(
    file_path: str,
    style: str = "google",
    output_path: Optional[str] = None,
    inplace: bool = False,
    model_name: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
    dry_run: bool = False,
    rel_path: str = "",
    repo_analyzer: Optional[RepoAnalyzer] = None,
) -> str:
  """Parse target file, inject missing docstrings, and write/output updated code."""
  if not os.path.exists(file_path):
    raise FileNotFoundError(f"Source file not found: {file_path}")

  with open(file_path, "r", encoding="utf-8") as f:
    source_code = f.read()

  # 1. Parse Python source file into AST
  tree = ast.parse(source_code, filename=file_path)

  # 2. Instantiate DocstringGenerator and Injector Transformer
  generator = DocstringGenerator(
      model_name=model_name, api_key=api_key, dry_run=dry_run
  )
  injector = DocstringInjector(
      generator=generator,
      style=style,
      rel_path=rel_path or os.path.basename(file_path),
      repo_analyzer=repo_analyzer,
  )

  # 3. Transform AST tree
  modified_tree = injector.visit(tree)
  ast.fix_missing_locations(modified_tree)

  print(f"[Summary] Injected {injector.injected_count} docstring(s).")

  # 4. Unparse updated AST tree back into Python code
  updated_code = ast.unparse(modified_tree)

  # 5. Output handling
  if inplace:
    with open(file_path, "w", encoding="utf-8") as f:
      f.write(updated_code)
    print(f"[Updated] Source file updated in-place: {file_path}")
  elif output_path:
    with open(output_path, "w", encoding="utf-8") as f:
      f.write(updated_code)
    print(f"[Output] Saved updated script to: {output_path}")

  return updated_code


def process_repository(
    dir_path: str,
    style: str = "google",
    inplace: bool = False,
    model_name: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
    dry_run: bool = False,
):
  """Processes an entire repository directory with cross-module dependency analysis."""
  if not os.path.exists(dir_path):
    raise FileNotFoundError(f"Target repository directory not found: {dir_path}")

  print("\n" + "=" * 60)
  print(" REPOSITORY-WIDE CROSS-MODULE DEPENDENCY ANALYSIS")
  print("=" * 60)
  analyzer = RepoAnalyzer(dir_path)
  print(
      f"[Analyzer] Discovered {len(analyzer.modules)} Python module(s) in"
      " repository."
  )
  print(
      f"[Analyzer] Indexed {len(analyzer.symbols)} unique defined symbols"
      " across modules.\n"
  )

  for rel_path in analyzer.modules.keys():
    full_path = os.path.join(analyzer.repo_dir, rel_path)
    print(f"\n--- Processing Repository File: {rel_path} ---")
    process_file(
        file_path=full_path,
        style=style,
        inplace=inplace,
        model_name=model_name,
        api_key=api_key,
        dry_run=dry_run,
        rel_path=rel_path,
        repo_analyzer=analyzer,
    )


def main():
  parser = argparse.ArgumentParser(
      description=(
          "Automated Python docstring injector using ast and google-genai SDK."
      )
  )
  parser.add_argument(
      "--file",
      "-f",
      help="Path to the single Python target file to process.",
  )
  parser.add_argument(
      "--dir",
      "-d",
      help=(
          "Path to repository directory to analyze and document cross-module"
          " dependencies."
      ),
  )
  parser.add_argument(
      "--style",
      "-s",
      choices=["google", "sphinx", "numpy"],
      default="google",
      help="Docstring format style (google, sphinx, numpy). Default: google.",
  )
  parser.add_argument(
      "--output",
      "-o",
      help="Path to output file (for single file mode).",
  )
  parser.add_argument(
      "--inplace",
      "-i",
      action="store_true",
      help="Overwrite target file(s) directly with updated docstrings.",
  )
  parser.add_argument(
      "--model",
      default="gemini-2.5-flash",
      help="Gemini model name. Default: gemini-2.5-flash.",
  )
  parser.add_argument(
      "--api-key",
      help=(
          "Gemini API key (optional if GEMINI_API_KEY environment variable is"
          " set)."
      ),
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help=(
          "Run without contacting Gemini API (useful for testing AST"
          " injection)."
      ),
  )
  parser.add_argument(
      "--check",
      action="store_true",
      help=(
          "CI/CD mode: Run documentation coverage audit without modifying"
          " files."
      ),
  )
  parser.add_argument(
      "--min-coverage",
      type=float,
      default=80.0,
      help=(
          "Minimum coverage percentage threshold for --check mode. Default:"
          " 80.0."
      ),
  )

  args = parser.parse_args()

  if not args.file and not args.dir:
    parser.error("Please specify either --file (-f) or --dir (-d).")

  try:
    if args.dir:
      process_repository(
          dir_path=args.dir,
          style=args.style,
          inplace=args.inplace,
          model_name=args.model,
          api_key=args.api_key,
          dry_run=args.dry_run,
      )
      return

    if args.check:
      passed = audit_file(file_path=args.file, min_coverage=args.min_coverage)
      sys.exit(0 if passed else 1)

    updated_code = process_file(
        file_path=args.file,
        style=args.style,
        output_path=args.output,
        inplace=args.inplace,
        model_name=args.model,
        api_key=args.api_key,
        dry_run=args.dry_run,
    )

    if not args.output and not args.inplace:
      print("\n--- GENERATED CODE ---\n")
      print(updated_code)

  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()