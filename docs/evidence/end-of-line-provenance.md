# Source hashes and Windows line endings

Evidence captures record the actual filesystem bytes served to the browser.
This Windows checkout has `core.autocrlf=true`; Git stores text with LF endings,
while existing working files can have CRLF or mixed endings. These raw byte
hashes can therefore differ from a fresh checkout even when the text and rendered
application are identical.

The final collectors preserve the captured raw SHA-256 values and separately
record SHA-256 after converting CRLF to LF. The normalized hash is explicitly a
portable text comparison, not a claim that normalized bytes were served during
the original capture. Binary screenshot and compressed evidence hashes receive
no text normalization. Historical baseline blobs come directly from their pinned
Git commit, with their own source hashes.

Use the capture date, phase-specific source mode, raw/normalized hashes, manifest,
fixtures, and screenshot references together. The eventual commit can include
evidence and documentation written after capture; a Git revision alone is not
a substitute for the captured application-source hashes.
