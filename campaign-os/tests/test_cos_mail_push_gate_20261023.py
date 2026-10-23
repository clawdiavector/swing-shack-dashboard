"""Agent mail hard gate (Kyle, 2026-10-23): a mail that refers to the wiki or the package only goes out
when what it refers to is committed and pushed."""
import argparse
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "cos_mail", ROOT / "plugins/campaign-os/skills/campaign-os-mail/scripts/cos_mail.py")
cos_mail = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cos_mail)


def sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo_with_origin(tmp_path, name):
    origin = tmp_path / f"{name}.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / name
    sh(tmp_path, "clone", "-q", str(origin), str(work))
    sh(work, "config", "user.email", "t@t")
    sh(work, "config", "user.name", "t")
    sh(work, "checkout", "-q", "-b", "main")
    return work


def commit(work, rel, text="x", push=True):
    f = work / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    sh(work, "add", rel)
    sh(work, "commit", "-q", "-m", rel)
    if push:
        sh(work, "push", "-q", "-u", "origin", "HEAD")
    return f


def args(**kw):
    base = dict(subject="s", message="m", how_to=None, wiki=[], file=[], kind="update")
    base.update(kw)
    return argparse.Namespace(**base)


def test_pushed_file_passes_and_shows_branch(tmp_path):
    work = repo_with_origin(tmp_path, "repo")
    f = commit(work, "plugins/campaign-os/README.md")
    ref = cos_mail.file_ref(str(f))
    assert ref["branch"] == "main"


def test_uncommitted_file_is_refused(tmp_path):
    work = repo_with_origin(tmp_path, "repo")
    f = commit(work, "a.py")
    f.write_text("changed")
    with pytest.raises(SystemExit, match="uncommitted"):
        cos_mail.file_ref(str(f))


def test_unpushed_commit_is_refused(tmp_path):
    work = repo_with_origin(tmp_path, "repo")
    commit(work, "a.py")
    f = commit(work, "a.py", "v2", push=False)
    with pytest.raises(SystemExit, match="not pushed"):
        cos_mail.file_ref(str(f))


def test_file_outside_git_is_refused(tmp_path):
    f = tmp_path / "loose.txt"
    f.write_text("x")
    with pytest.raises(SystemExit, match="not in a git repo"):
        cos_mail.file_ref(str(f))


def test_wiki_page_named_in_text_must_be_passed(tmp_path):
    a = args(message="Read runbooks/add-posts-to-calendar-for-approval-2026-10-23.md first.")
    with pytest.raises(SystemExit, match="--wiki"):
        cos_mail.push_gate(a)


def test_wiki_page_named_and_passed_is_fine():
    a = args(message="See runbooks/x.md", wiki=["/home/me/CampaignOSKnowledgeBase/CampaignOS/runbooks/x.md"])
    cos_mail.push_gate(a)


def test_package_path_in_text_must_be_passed():
    a = args(message="The renderer is campaign-os/scripts/render_post.py.")
    with pytest.raises(SystemExit, match="--file"):
        cos_mail.push_gate(a)


def test_package_kind_needs_files():
    with pytest.raises(SystemExit, match="--file"):
        cos_mail.push_gate(args(kind="package"))


def test_branch_not_on_origin_is_refused(tmp_path, monkeypatch):
    work = repo_with_origin(tmp_path, "repo")
    commit(work, "plugins/campaign-os/README.md")
    monkeypatch.setattr(cos_mail, "_package_repo", lambda: work)
    with pytest.raises(SystemExit, match="not on origin"):
        cos_mail.check_branch("feat/never-pushed")


def test_branch_ahead_of_origin_is_refused(tmp_path, monkeypatch):
    work = repo_with_origin(tmp_path, "repo")
    commit(work, "plugins/campaign-os/README.md")
    sh(work, "checkout", "-q", "-b", "feat/x")
    commit(work, "b.py")
    commit(work, "b.py", "v2", push=False)
    sh(work, "checkout", "-q", "main")
    monkeypatch.setattr(cos_mail, "_package_repo", lambda: work)
    with pytest.raises(SystemExit, match="not pushed"):
        cos_mail.check_branch("feat/x")


def test_pushed_branch_passes(tmp_path, monkeypatch):
    work = repo_with_origin(tmp_path, "repo")
    commit(work, "plugins/campaign-os/README.md")
    sh(work, "checkout", "-q", "-b", "feat/y")
    commit(work, "c.py")
    monkeypatch.setattr(cos_mail, "_package_repo", lambda: work)
    cos_mail.check_branch("feat/y")


def test_wiki_clone_with_unpushed_commits_is_refused(tmp_path):
    work = repo_with_origin(tmp_path, "campaign-os-wiki")
    page = commit(work, "CampaignOS/runbooks/a.md")
    assert cos_mail.wiki_ref(str(page))["path"] == "CampaignOS/runbooks/a.md"
    commit(work, "CampaignOS/runbooks/b.md", push=False)
    with pytest.raises(SystemExit, match="not pushed"):
        cos_mail.wiki_ref(str(page))
