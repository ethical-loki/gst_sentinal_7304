import re
from pathlib import Path

ROOT = Path(r"c:\Users\User\OneDrive\Desktop\GST_Sentinal")

FILES = [
    ROOT / "static" / "ingestion.html",
    ROOT / "static" / "converter.html",
    ROOT / "frontend" / "ingestion.html",
    ROOT / "frontend" / "converter.html",
    ROOT / "src" / "ui" / "ingestion.html",
    ROOT / "gst_sentinal_7304" / "static" / "ingestion.html",
    ROOT / "gst_sentinal_7304" / "static" / "converter.html",
    ROOT / "gst_sentinal_7304" / "frontend" / "ingestion.html",
    ROOT / "gst_sentinal_7304" / "frontend" / "converter.html",
    ROOT / "gst_sentinal_7304" / "src" / "ui" / "ingestion.html",
]

def fix_file(filepath: Path):
    if not filepath.exists():
        print(f"Skipping non-existent: {filepath}")
        return
    content = filepath.read_text(encoding="utf-8")

    # 1. Remove premature handledTypes.add('date') and handledTypes.add('docno')
    content = re.sub(
        r"if\s*\(\s*isDateValid\s*\|\|\s*isDateJustPatched\s*\)\s*\{\s*handledTypes\.add\('date'\);\s*\}",
        "if (isDateJustPatched) {\n            handledTypes.add('date');\n        }",
        content
    )
    content = re.sub(
        r"if\s*\(\s*isDocNoValid\s*\|\|\s*isDocnoJustPatched\s*\)\s*\{\s*handledTypes\.add\('docno'\);\s*\}",
        "if (isDocnoJustPatched) {\n            handledTypes.add('docno');\n        }",
        content
    )

    # 2. Fix activeTopic detection for date and docno
    content = re.sub(
        r"\}\s*else\s+if\s*\(\s*!isDocNoValid\s*&&\s*!isDocnoJustPatched\s*&&\s*actions\.some\(a\s*=>\s*/set invoice no\|invoice number\|docno/i\.test\(a\)\)\)\s*\{\s*activeTopic\s*=\s*'docno';",
        "} else if (!isDocnoJustPatched && actions.some(a => /set invoice no|invoice number|docno/i.test(a))) {\n            activeTopic = 'docno';",
        content
    )
    content = re.sub(
        r"\}\s*else\s+if\s*\(\s*!isDateValid\s*&&\s*!isDateJustPatched\s*&&\s*actions\.some\(a\s*=>\s*/change date to\|set date:/i\.test\(a\)\)\)\s*\{\s*activeTopic\s*=\s*'date';",
        "} else if (!isDateJustPatched && actions.some(a => /change date to|set date:|today|yesterday/i.test(a))) {\n            activeTopic = 'date';",
        content
    )

    # 3. Fix tailPrompt detection
    content = re.sub(
        r"\}\s*else\s+if\s*\(\s*!isDocNoValid\s*&&\s*!isDocnoJustPatched\s*&&\s*\(tailPrompt\.includes\('invoice number'\)",
        "} else if (!isDocnoJustPatched && (tailPrompt.includes('invoice number')",
        content
    )
    content = re.sub(
        r"\}\s*else\s+if\s*\(\s*!isDateValid\s*&&\s*!isDateJustPatched\s*&&\s*\(tailPrompt\.includes\('document date'\)",
        "} else if (!isDateJustPatched && (tailPrompt.includes('document date')",
        content
    )

    # Also check if tailPrompt includes docdt
    content = re.sub(
        r"tailPrompt\.includes\('document date'\)\s*\|\|\s*tailPrompt\.includes\('change the document date'\)\s*\|\|\s*tailPrompt\.includes\('invoice date'\)\s*\|\|\s*tailPrompt\.includes\('date to within'\)",
        "tailPrompt.includes('document date') || tailPrompt.includes('change the document date') || tailPrompt.includes('invoice date') || tailPrompt.includes('date to within') || tailPrompt.includes('docdt')",
        content
    )

    # 4. In renderDocnoBox, ensure it doesn't return early if prompt is asking for docno
    old_render_docno_start = r"const renderDocnoBox = \(\) => \{\s*if \((?:isDocNoValid \|\| )?isDocnoJustPatched \|\| renderedBoxCount > 0 \|\| handledTypes\.has\('docno'\)\) return;"
    new_render_docno_start = (
        "const renderDocnoBox = () => {\n"
        "            if (isDocnoJustPatched || renderedBoxCount > 0 || handledTypes.has('docno')) return;"
    )
    content = re.sub(old_render_docno_start, new_render_docno_start, content)

    # 5. In renderDateBox, ensure it doesn't return early if prompt is asking for date
    old_render_date_start = r"const renderDateBox = \(\) => \{\s*if \((?:isDateValid \|\| )?isDateJustPatched \|\| renderedBoxCount > 0 \|\| handledTypes\.has\('date'\)\) return;"
    new_render_date_start = (
        "const renderDateBox = () => {\n"
        "            if (isDateJustPatched || renderedBoxCount > 0 || handledTypes.has('date')) return;"
    )
    content = re.sub(old_render_date_start, new_render_date_start, content)

    # 6. Make sure hasDatePrompt detects [docdt1.docdt] or docdt in tailPrompt
    content = re.sub(
        r"tailPrompt\.includes\('change the document date'\)\);",
        "tailPrompt.includes('change the document date') || tailPrompt.includes('docdt') || tailPrompt.includes('set date:'));",
        content
    )

    # 7. In fallback sequence, render docno or date box if not patched and either invalid or prompted
    content = re.sub(
        r"if\s*\(\s*renderedBoxCount === 0\s*&&\s*!isDocNoValid\s*&&\s*!isDocnoJustPatched\s*\)\s*renderDocnoBox\(\);",
        "if (renderedBoxCount === 0 && !isDocnoJustPatched && (!isDocNoValid || actions.some(a => /invoice no|docno/i.test(a)))) renderDocnoBox();",
        content
    )
    content = re.sub(
        r"if\s*\(\s*renderedBoxCount === 0\s*&&\s*!isDateValid\s*&&\s*!isDateJustPatched\s*\)\s*renderDateBox\(\);",
        "if (renderedBoxCount === 0 && !isDateJustPatched && (!isDateValid || actions.some(a => /date/i.test(a)))) renderDateBox();",
        content
    )

    # 8. Skip list for standalone buttons
    content = re.sub(
        r"\(handledTypes\.has\('date'\)\s*&&\s*\(actL\.includes\('apply date'\)[\s\S]*?change date to yesterday'\)\)\)",
        "(handledTypes.has('date') && (actL.includes('apply date') || actL.includes('set today') || actL.includes('change date to today') || actL.includes('change date to yesterday') || actL.includes('set date:')))",
        content
    )
    content = re.sub(
        r"\(handledTypes\.has\('docno'\)\s*&&\s*\(actL\.includes\('invoice no'\)[\s\S]*?apply invoice no'\)\)\)",
        "(handledTypes.has('docno') && (actL.includes('invoice no') || actL.includes('docno') || actL.includes('set invoice') || actL.includes('apply invoice no')))",
        content
    )

    filepath.write_text(content, encoding="utf-8")
    print(f"Fixed: {filepath}")

for f in FILES:
    fix_file(f)
