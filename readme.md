# Walkthrough - Python CLI Docstring Generator (`doc_generator.py`)

We have built `doc_generator.py`, an automated Python CLI tool that parses Python files, identifies functions missing docstrings using Python's `ast` module, generates docstrings using the `google-genai` SDK (`gemini-2.5-flash`), and injects them back into the source code via `ast.NodeTransformer` and `ast.unparse()`.

## Files Created

- [doc_generator.py](file:///C:/Users/HP/.gemini/antigravity/scratch/doc_generator/doc_generator.py): The main CLI script.
- [sample_test.py](file:///C:/Users/HP/.gemini/antigravity/scratch/doc_generator/sample_test.py): Test file containing sync, async, and class functions.
- [requirements.txt](file:///C:/Users/HP/.gemini/antigravity/scratch/doc_generator/requirements.txt): Python dependency file (`google-genai`).

---

## Key Features Implemented

1. **AST Parsing & Filtering**:
   - Parses code into AST with `ast.parse()`.
   - Traverses function nodes (`ast.FunctionDef`, `ast.AsyncFunctionDef`).
   - Uses `ast.get_docstring(node)` to detect missing docstrings while skipping functions that already have docstrings.

2. **Google GenAI SDK Integration**:
   - Integrates `from google import genai` (`google-genai>=0.1.0`).
   - Generates docstrings with `gemini-2.5-flash` model (with automatic fallback to `gemini-2.0-flash` or `gemini-1.5-flash`).
   - Supports 3 standard docstring formats: `google`, `sphinx`, and `numpy`.

3. **AST Node Transformer**:
   - Uses `ast.NodeTransformer` (`DocstringInjector`) to construct `ast.Expr(value=ast.Constant(value=docstring))` and insert it as the first statement in `node.body`.
   - Calls `ast.fix_missing_locations()` and converts back to formatted code using `ast.unparse()`.

4. **Argparse CLI Interface**:
   - `--file` / `-f`: Input Python file path (Required).
   - `--style` / `-s`: Choice of `google`, `sphinx`, or `numpy` (Default: `google`).
   - `--output` / `-o`: Path to save updated script.
   - `--inplace` / `-i`: Overwrite input file directly.
   - `--model`: Gemini model (Default: `gemini-2.5-flash`).
   - `--api-key`: API key flag (or reads `GEMINI_API_KEY` from environment).
   - `--dry-run`: Mode for testing AST transformation without network requests.

---

## Usage Examples

### 1. View Help Command
```bash
python doc_generator.py --help
```

### 2. Generate Google Style Docstrings with Gemini API Key
```powershell
$env:GEMINI_API_KEY="your_api_key_here"
python doc_generator.py --file sample_test.py --style google --output updated_sample.py
```
Or pass the API key directly:
```powershell
python doc_generator.py --file sample_test.py --style google --api-key "your_api_key_here" --output updated_sample.py
```

### 3. Update File In-Place with NumPy Style Docstrings
```powershell
python doc_generator.py --file sample_test.py --style numpy --inplace
```

### 4. Test Offline (Dry-Run Mode)
```powershell
python doc_generator.py --file sample_test.py --style sphinx --dry-run
```

---

## Verification Results

- Tested AST docstring detection on `sample_test.py` (properly detected 4 undocumented functions and skipped 1 already-documented function).
- Verified `ast.unparse()` produces syntactically valid Python code.
- Tested and verified execution of generated output with `python -c "import generated_sample"`.

