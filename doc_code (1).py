#!/usr/bin/env python3
"""
doc_generator.py - Automated Python Docstring Injector using AST and Google GenAI SDK.
"""

import argparse
import ast
import os
import sys
from typing import Optional

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
    )
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
    if (text.startswith('"""') and text.endswith('"""')) or (text.startswith("'''") and text.endswith("'''")):
        text = text[3:-3].strip()
    elif (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
        
    return text


class DocstringGenerator:
    """Communicates with Google GenAI SDK to generate docstrings."""
    
    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        dry_run: bool = False
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

    def generate_docstring(self, func_name: str, func_code: str, style: str) -> str:
        """Requests Gemini API (or generates mock) to produce docstring for given function code."""
        if self.dry_run:
            if style == "google":
                return (
                    f"Auto-generated Google docstring for {func_name}.\n\n"
                    f"Args:\n"
                    f"    *args: Function arguments.\n\n"
                    f"Returns:\n"
                    f"    Any: Function result."
                )
            elif style == "sphinx":
                return (
                    f"Auto-generated Sphinx docstring for {func_name}.\n\n"
                    f":param args: Function arguments.\n"
                    f":returns: Function result.\n"
                    f":rtype: Any"
                )
            elif style == "numpy":
                return (
                    f"Auto-generated NumPy docstring for {func_name}.\n\n"
                    f"Parameters\n"
                    f"----------\n"
                    f"args\n"
                    f"    Function arguments.\n\n"
                    f"Returns\n"
                    f"-------\n"
                    f"Any\n"
                    f"    Function result."
                )

        style_guide = STYLE_PROMPTS.get(style.lower(), STYLE_PROMPTS["google"])
        
        prompt = (
            f"You are a professional Python documentation assistant.\n"
            f"Generate ONLY a python docstring for the following function code.\n"
            f"Follow the {style.upper()} docstring convention exact structure:\n"
            f"{style_guide}\n\n"
            f"RULES:\n"
            f"1. DO NOT include the function signature or function body.\n"
            f"2. DO NOT wrap the output in triple backticks (```) or code blocks.\n"
            f"3. DO NOT include triple quotes (\x22\x22\x22) in your response; return raw text only.\n"
            f"4. Be accurate with types, parameter names, and return values.\n\n"
            f"Function Source Code:\n"
            f"```python\n{func_code}\n```"
        )
        
        model_candidates = [self.model_name]
        if self.model_name == "gemini-2.5-flash":
            model_candidates.extend(["gemini-2.0-flash", "gemini-1.5-flash"])

        last_error = None
        for model in model_candidates:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                if response and response.text:
                    return clean_docstring_response(response.text)
            except Exception as e:
                last_error = e
                # Retry with fallback model if model not found
                if "404" in str(e) or "NOT_FOUND" in str(e):
                    continue
                else:
                    raise e
        
        print(f"[Error generating docstring for '{func_name}']: {last_error}", file=sys.stderr)
        raise last_error


class DocstringInjector(ast.NodeTransformer):
    """AST NodeTransformer that identifies undocumented functions and injects docstrings."""
    
    def __init__(self, generator: DocstringGenerator, style: str = "google"):
        super().__init__()
        self.generator = generator
        self.style = style
        self.injected_count = 0

    def _process_function(self, node: ast.AST) -> ast.AST:
        # Check if function already has a docstring
        existing_doc = ast.get_docstring(node)
        if existing_doc:
            print(f"[Skip] Function '{node.name}' already has a docstring.")
            return self.generic_visit(node)
        
        print(f"[Injecting] Generating '{self.style}' docstring for function '{node.name}'...")
        
        # Get unparsed code for function node
        func_code = ast.unparse(node)
        
        # Generate docstring
        docstring_text = self.generator.generate_docstring(node.name, func_code, self.style)
        
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


def process_file(
    file_path: str,
    style: str = "google",
    output_path: Optional[str] = None,
    inplace: bool = False,
    model_name: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
    dry_run: bool = False
) -> str:
    """Parse target file, inject missing docstrings, and write/output updated code."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    # 1. Parse Python source file into AST
    tree = ast.parse(source_code, filename=file_path)

    # 2. Instantiate DocstringGenerator and Injector Transformer
    generator = DocstringGenerator(model_name=model_name, api_key=api_key, dry_run=dry_run)
    injector = DocstringInjector(generator=generator, style=style)

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


def main():
    parser = argparse.ArgumentParser(
        description="Automated Python docstring injector using ast and google-genai SDK."
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        help="Path to the Python target file to process."
    )
    parser.add_argument(
        "--style", "-s",
        choices=["google", "sphinx", "numpy"],
        default="google",
        help="Docstring format style (google, sphinx, numpy). Default: google."
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to output file. If omitted and --inplace is not set, prints result to stdout."
    )
    parser.add_argument(
        "--inplace", "-i",
        action="store_true",
        help="Overwrite the input file directly with updated docstrings."
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model name. Default: gemini-2.5-flash."
    )
    parser.add_argument(
        "--api-key",
        help="Gemini API key (optional if GEMINI_API_KEY environment variable is set)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without contacting Gemini API (useful for testing AST injection)."
    )

    args = parser.parse_args()

    try:
        updated_code = process_file(
            file_path=args.file,
            style=args.style,
            output_path=args.output,
            inplace=args.inplace,
            model_name=args.model,
            api_key=args.api_key,
            dry_run=args.dry_run
        )
        
        if not args.output and not args.inplace:
            print("\n--- GENERATED CODE ---\n")
            print(updated_code)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
