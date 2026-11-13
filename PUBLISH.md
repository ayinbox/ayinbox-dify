# Publishing to the Dify Marketplace

The Dify Marketplace lists a plugin once a pull request that adds its `.difypkg` is merged into [`langgenius/dify-plugins`](https://github.com/langgenius/dify-plugins). There is no registry token and nothing to publish from this repository: the package goes in through that pull request, and every later version goes in the same way.

Rules this is based on (checked 2026-11-13): the `langgenius/dify-plugins` README, `docs/plugin-submission-requirements.md`, `docs/marketplace-curation-policy.md`, `.github/pull_request_template.md` and the `Pre Check Plugin` and `Governance` workflows, which run the validators in `langgenius/dify-marketplace-toolkit`.

## 1. One-time setup

- This repository (`ayinbox/ayinbox-dify`) must be public before the pull request: reviewers and the README check follow the `repo` link in `manifest.yaml`.
- A GitHub account to open the pull request from, with a fork of `langgenius/dify-plugins`.
- Test the plugin on Dify Cloud and on a Dify Community Edition install with a real AY Inbox key (the PR template asks for both, or for the limitation to be written down). Remote debugging works with a debug key from the Dify plugin page: copy it into `.env` as `INSTALL_METHOD=remote`, `REMOTE_INSTALL_URL` and `REMOTE_INSTALL_KEY`, then run `python -m main`. `.env` is ignored by git and by the package.

## 2. Build the package

The Dify CLI is a single binary from the `langgenius/dify-plugin-daemon` releases. Keep it in `.tools/` (ignored by git and by the package) and check its SHA-256 against the digest GitHub shows for the release asset.

```sh
mkdir -p .tools
# macOS on Apple silicon; use dify-plugin-linux-amd64 on Linux (CI pins its checksum in ci.yml)
curl -fL -o .tools/dify https://github.com/langgenius/dify-plugin-daemon/releases/download/0.6.15/dify-plugin-darwin-arm64
echo "447f51bd67fca78769cfad57de1fcb530dfb28072524889cb3470bdce200c3f3  .tools/dify" | shasum -a 256 -c
chmod +x .tools/dify

mkdir -p dist
.tools/dify plugin package . -o dist/ayinbox-0.1.0.difypkg
unzip -Z1 dist/ayinbox-0.1.0.difypkg   # only runtime files: no tests, .git, .venv, caches
```

`.difyignore` keeps development files out of the package. CI builds the same package on every push and uploads it as the `ayinbox-difypkg` artifact.

Before submitting, run the Marketplace validator on the package (CI runs it too; it needs `yq`):

```sh
git clone https://github.com/langgenius/dify-marketplace-toolkit.git /tmp/toolkit
python3 /tmp/toolkit/validator/validate-difypkg.py dist/ayinbox-0.1.0.difypkg --output-dir /tmp/validation --pr-body-file pr-body.md
```

## 3. Open the pull request

```sh
gh repo fork langgenius/dify-plugins --clone --remote
cd dify-plugins
git checkout -b ayinbox-0.1.0
mkdir -p ayinbox/ayinbox
cp ../ayinbox-dify/dist/ayinbox-0.1.0.difypkg ayinbox/ayinbox/
git add ayinbox/ayinbox/ayinbox-0.1.0.difypkg
git commit -m "Add AY Inbox plugin (ayinbox/ayinbox) 0.1.0"
git push -u origin ayinbox-0.1.0
gh pr create -R langgenius/dify-plugins --base main --title "Add AY Inbox plugin (ayinbox/ayinbox) 0.1.0" --body-file pr-body.md
```

The pull request adds exactly one file, `ayinbox/ayinbox/ayinbox-0.1.0.difypkg`. The directory is `<author>/<plugin name>/` and must match `author` and `name` in `manifest.yaml`. Source code does not go in that repository.

### PR text (`pr-body.md`)

Fill in the two "Local validation" results and the testing line before submitting; tick a box only when it is true.

````markdown
# Plugin Submission

## Plugin information

- **Author**: ayinbox
- **Plugin name**: ayinbox
- **Version**: 0.1.0
- **Source repository**: https://github.com/ayinbox/ayinbox-dify
- **Contact**: team@ayinbox.com

## Submission type

- [x] New plugin
- [ ] Version update

## What changed

New plugin for AY Inbox (https://ayinbox.com), a hosted cold email platform. I work on AY Inbox.

It adds 14 tools for agents, chatflows and workflows: who am I, list campaigns, get campaign (with stats), create campaign draft, pause campaign, search contacts, create contact, update contact, list mailboxes, list inbox threads, get inbox thread, save email draft, list suppressions and add suppressions. Each tool returns a JSON message and a short text summary. One credential, an AY Inbox API key, checked against `GET /me`.

No tool sends email, starts or resumes a campaign, adds a contact to a campaign or removes a suppression. Draft campaigns and email drafts wait for a person in AY Inbox.

## Risk level

- [ ] Low risk
- [x] Medium risk
- [ ] High risk

Medium: the plugin performs write actions in a third-party service (contacts, draft campaigns, email drafts, suppressions, pausing a campaign) and handles personal data that is not highly sensitive (contact names, email addresses, email text). It only calls one fixed, documented HTTPS API.

## Required checks

- [x] I have read and followed the [Marketplace submission requirements](https://github.com/langgenius/dify-plugins/blob/main/docs/plugin-submission-requirements.md).
- [x] I have read and comply with the [Plugin Development Guidelines](https://docs.dify.ai/en/develop-plugin/publishing/standards/contributor-covenant-code-of-conduct).
- [ ] I tested this plugin on Dify Community Edition and Dify Cloud, or documented any limitation below.
- [x] The package contains only files needed at runtime.
- [x] The package does not contain secrets, local credentials, `.env` files, `.git` directories, virtual environments, caches, logs, or IDE files.
- [x] The package does not contain executables or bundled binaries, or I explained why they are required below.
- [x] The plugin README includes setup steps, usage instructions, required APIs or credentials, connection requirements, and the source repository link.
- [x] The plugin includes `PRIVACY.md` or a hosted privacy policy, and `manifest.yaml` references it.
- [x] All user-facing text is primarily in English, with any localized README files following the [i18n guidance](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/multilingual-readme).

## Security and privacy notes

None of the listed sensitive capabilities: no command or code execution, SQL, SSH/SFTP, browser automation, file operations, arbitrary URL fetching or proxying.

- Network: one fixed host, `api.ayinbox.com`, declared under `network.domains`. The base URL cannot be changed and redirects are not followed.
- Data sent: the API key (Authorization header) and the tool arguments. The plugin stores nothing and sends no telemetry.
- Personal data: contact details and email text from the user's own AY Inbox workspace. Inbox text is marked untrusted in tool output so agents treat it as data.
- Errors carry the API's status, code and request id, never the key. Requests time out after 30 seconds; a POST or PATCH without an idempotency key is never retried except after a 429.

## Local validation

```
python -m pytest -q        # <N> passed
.tools/dify plugin package . -o dist/ayinbox-0.1.0.difypkg   # Dify CLI 0.6.15
python3 validator/validate-difypkg.py ayinbox-0.1.0.difypkg --output-dir ./validation --pr-body-file pr-body.md   # <result>
```

## Reviewer notes

AY Inbox access is invite only for now; a reviewer who wants a test workspace can ask at team@ayinbox.com.
````

## 4. What reviewers and the checks look at

Automated, on the pull request:

- Exactly one `.difypkg` added, at `<author>/<plugin>/<plugin>-<version>.difypkg`; no other plugin's files in that directory and no package in the author root.
- `manifest.yaml`: `author`, `name`, `version`, `type: plugin`, `icon`, `plugins`, `privacy`, `repo` (an allowed host such as github.com), `contact` (an email), `label.en_US`, `description.en_US`, `meta.*`, and a recommended `meta.minimum_dify_version`. The author must not contain `dify` or `langgenius`.
- `tags`: a non-empty list from the controlled vocabulary (this plugin uses `business` and `productivity`).
- The version must not already exist on the Marketplace.
- `PRIVACY.md` exists, is not the template text, and covers what is collected, stored, logged and shared.
- `README.md` links the source repository, is in English (no CJK outside code blocks) and mentions setup, usage, credentials and connection requirements.
- The icon in `_assets/` exists and is not the template icon.
- No secrets, `.env`, `.git`, virtualenvs, caches, logs, IDE files or binaries in the package; size limits.
- `requirements.txt` installs, dependencies are scanned for known vulnerabilities, the plugin installs and starts in a test daemon, and the package re-packages cleanly.
- The PR body keeps the template's fields and headings, selects exactly one submission type and one risk level, and is in English.
- Near-duplicate detection against the author's other plugins (a warning, or a block on a same-author name collision).

By a person: whether the risk level and the security notes match what the code does, whether the plugin is useful and not a duplicate, and whether the testing claims hold.

## 5. Later versions

Bump `version` in `manifest.yaml` (and `VERSION` in `ayinbox_api/client.py`, which sets the user agent; a test checks they match), add a `CHANGELOG.md` entry, build the new package, and open a pull request whose only change is the new `.difypkg` in `ayinbox/ayinbox/`, with "Version update" ticked. The repository keeps only the current version of a plugin, so the old package leaves that directory when the new one arrives; keep older packages as GitHub releases of this repository. Document any breaking change in `README.md` and in the PR.
