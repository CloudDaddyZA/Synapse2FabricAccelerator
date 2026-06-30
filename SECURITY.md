# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in the Synapse to Fabric Migration
Accelerator, please report it responsibly.

- **Preferred:** Open a private report via GitHub's
  [Security Advisories](https://github.com/CloudDaddyZA/Synapse2FabricAccelerator/security/advisories/new)
  ("Report a vulnerability").
- Do **not** open a public issue for security-sensitive reports.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce or a proof of concept.
- Affected version, commit, or configuration.

You can expect an acknowledgement within a few business days. Once the issue is
validated, a fix will be prioritized and you will be credited (unless you prefer
to remain anonymous).

## Supported Versions

This project is distributed as a source accelerator and is maintained on the
`main` branch. Security fixes are applied to `main`; there is no separate
long-term support branch.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |

## Scope and Handling of Sensitive Data

This tool audits Azure Synapse environments. To keep your data safe:

- **Never commit secrets.** Credentials are resolved at runtime via
  [Azure Identity](https://learn.microsoft.com/azure/developer/python/sdk/authentication/overview);
  no keys or connection strings are stored in the repository.
- Generated audit output (`output/`) and Power BI extracts (`powerbi/`) are
  git-ignored to prevent accidental disclosure of workspace inventory and
  resource names.
- Review reports before sharing externally — they may contain workspace,
  pipeline, and resource names specific to your environment.

Secret scanning and push protection are enabled on this repository to help
prevent accidental credential commits.
