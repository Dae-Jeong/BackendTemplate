"""Render canonical Markdown directly; never publish the repository tree."""

from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files


def on_files(files: Files, *, config: MkDocsConfig) -> Files:
    root = Path(config.config_file_path).parent
    sources = [root / "README.md", root / "RUNBOOK.md"]
    for language in ("python", "ts", "java", "kotlin", "ruby"):
        sources.extend(sorted((root / language).glob("*/README.md")))
    sources.extend(sorted((root / "design").rglob("*.md")))
    # Keep Material's assets, but exclude every file from the tooling directory.
    for file in list(files):
        if file.src_dir == config.docs_dir:
            files.remove(file)
    for source in sources:
        files.append(
            File.generated(
                config,
                source.relative_to(root).as_posix(),
                abs_src_path=str(source),
            )
        )
    return files
