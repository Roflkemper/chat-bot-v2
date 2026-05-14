# encoding_safety

**Trigger:** writing any .md / .txt / .csv / .json file via PowerShell or Python on Windows; printing Cyrillic text to Windows terminal.

---

## PowerShell: always explicit UTF-8 no-BOM

```powershell
# CORRECT
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($path, $content, $utf8)

# WRONG — uses system locale (CP1251 on RU Windows)
Out-File, Set-Content, > redirection
```

Verify after write:
```powershell
Get-Content $path -Encoding UTF8 | Select-Object -First 5
```

## Python: stdout encoding on Windows terminal

Windows terminal may use CP1251/CP866. Fix:
```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

Or use `errors='replace'` in print calls with Cyrillic messages going to console.

## Diagnosis

- File bytes valid UTF-8 but terminal shows `?` → terminal encoding issue, file is fine
- File bytes invalid UTF-8 → file is broken, re-save with explicit UTF-8

## Prevention rule

Never assume default encoding on Windows. Always specify explicitly.
If mojibake appears in terminal output — diagnose file bytes first before re-encoding.
Re-encoding a valid UTF-8 file as CP1251→UTF-8 creates double-encoded mojibake.
