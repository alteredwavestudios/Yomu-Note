# Security policy

Yomu Note is a **preview application**, not a sandbox for arbitrary hostile PDFs or notebooks. Imported files may be processed by PDFium, Pillow, SQLite, document conversion utilities and Tesseract.

Please **do not publish a working exploit or private notebook in a public issue**. To report a sensitive security issue, use the repository's **Security → Report a vulnerability** feature if private vulnerability reporting has been enabled. Otherwise contact the repository maintainer privately through a channel listed on the maintainer's GitHub profile; do not post proof-of-concept files publicly.

For ordinary bugs, use GitHub Issues and a redacted, non-personal reproduction example. Current audit/known limitations: [SECURITY_AUDIT_081A.md](SECURITY_AUDIT_081A.md).

Supported release line during preview: **v0.8.1b**; older preview versions may lack important safety checks. Keep a separate copy of important `.yomunote` notebooks.
