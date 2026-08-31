# Security Policy

Report security issues privately to the repository maintainers rather than in a
public issue.

The project treats PDFs, DOCX files, HTML, model responses, and remote metadata
as untrusted input. Run document parsers with the least privileges available.
API credentials must be supplied through environment variables and are never
written to manifests or logs.

Do not expose an unauthenticated local inference endpoint to an untrusted
network. Review generated Markdown before publishing it because source
documents may contain active links or adversarial text.
