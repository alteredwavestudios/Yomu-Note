"""One shared lock for every use of the PDFium library.

PDFium is the library that reads and draws PDF pages.
It cannot safely be called by two Python threads at once.

A *lock* works like a key for a room: only the thread
holding the key may enter. Other threads wait their turn.

We use an RLock (a re-entrant lock) so a function that
already holds the lock may safely call another function
that also asks for the same lock.

IMPORTANT: Keep the lock around the entire lifetime of
PDF objects, including closing pages and documents.
A lock around just page.render() is not sufficient.
"""

import threading

PDFIUM_LOCK = threading.RLock()
