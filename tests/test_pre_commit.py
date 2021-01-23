import sys
from textwrap import dedent

import pytest
from git.exc import HookExecutionError
from nbformat.v4.nbbase import new_markdown_cell, new_notebook
from pre_commit.main import main as pre_commit

from jupytext import read, write
from jupytext.cli import jupytext

if sys.platform.startswith("win"):  # pragma: nocover
    # The tests below fail in the Windows plan (which does not upload coverage)
    # https://github.com/mwouts/jupytext/runs/1745075455
    pytestmark = pytest.mark.skip(
        "OSError: [WinError 193] %1 is not a valid Win32 application"
    )


def test_pre_commit_hook_for_new_file(
    tmpdir, cwd_tmpdir, tmp_repo, capsys, jupytext_repo_root, jupytext_repo_rev
):
    pre_commit_config_yaml = dedent(
        f"""
        repos:
        - repo: {jupytext_repo_root}
          rev: {jupytext_repo_rev}
          hooks:
          - id: jupytext
            args: [--sync]
        """
    )
    tmpdir.join(".pre-commit-config.yaml").write(pre_commit_config_yaml)

    tmp_repo.git.add(".pre-commit-config.yaml")
    pre_commit(["install", "--install-hooks", "-f"])

    # write test notebook and sync it to py:percent
    nb = new_notebook(cells=[new_markdown_cell("A short notebook")])
    write(nb, "test.ipynb")

    jupytext(["--set-formats", "ipynb,py:percent", "test.ipynb"])

    # try to commit it, should fail because the py version hasn't been added
    tmp_repo.git.add("test.ipynb")
    with pytest.raises(
        HookExecutionError,
        match="Please run 'git add test.py'",
    ):
        tmp_repo.index.commit("failing")

    # add the py file, now the commit will succeed
    tmp_repo.git.add("test.py")
    tmp_repo.index.commit("passing")
    assert "test.ipynb" in tmp_repo.tree()
    assert "test.py" in tmp_repo.tree()

    # modify the ipynb file
    nb = read("test.ipynb")
    nb.cells.append(new_markdown_cell("A new cell"))
    write(nb, "test.ipynb")

    tmp_repo.git.add("test.ipynb")
    # Don't add the .py version yet (1), otherwise it may overwrite the .ipynb version!
    with pytest.raises(
        HookExecutionError,
        match="files were modified by this hook",
    ):
        tmp_repo.index.commit("failing")

    # the text file has been updated
    assert "A new cell" in tmpdir.join("test.py").read()

    print("===== test.py =====")
    print(tmpdir.join("test.py").read())
    print("===== test.ipynb =====")
    print(tmpdir.join("test.ipynb").read())

    # trying to commit should fails again because we forgot to add the .py version
    # But (2) it reverts the ipynb file to its previous version!!!
    with pytest.raises(
        HookExecutionError,
        match="Please run 'git add test.ipynb'",  # TODO this is incorrect! should be 'git add test.py'
    ):
        tmp_repo.index.commit("still failing")

    print("===== test.py =====")
    print(tmpdir.join("test.py").read())
    print("===== test.ipynb =====")
    print(tmpdir.join("test.ipynb").read())

    nb = read("test.ipynb")
    assert len(nb.cells) == 2, "Oh now, the notebook was reverted to its previous state"

    # add the text file, now the commit will succeed
    # tmp_repo.git.add("test.py")
    # tmp_repo.index.commit("passing")


def test_pre_commit_hook_for_existing_changed_file(
    tmpdir, cwd_tmpdir, tmp_repo, capsys, jupytext_repo_root, jupytext_repo_rev
):
    # set up the tmpdir repo with pre-commit
    pre_commit_config_yaml = dedent(
        f"""
        repos:
        - repo: {jupytext_repo_root}
          rev: {jupytext_repo_rev}
          hooks:
          - id: jupytext
            args: [--from, ipynb, --to, "py:percent"]
        """
    )
    tmpdir.join(".pre-commit-config.yaml").write(pre_commit_config_yaml)
    tmp_repo.git.add(".pre-commit-config.yaml")
    pre_commit(["install", "--install-hooks"])

    # write test notebook and output file
    nb = new_notebook(cells=[new_markdown_cell("A short notebook")])
    write(nb, "test.ipynb")
    jupytext(["--from", "ipynb", "--to", "py:percent", "test.ipynb"])

    tmp_repo.git.add(".")
    tmp_repo.index.commit("test")

    # make a change to the notebook
    nb = new_notebook(cells=[new_markdown_cell("Some other text")])
    write(nb, "test.ipynb")

    tmp_repo.git.add("test.ipynb")
    # now a commit will fail, and keep failing until we add the new
    # changes made to the existing output to the index ourselves
    with pytest.raises(HookExecutionError, match="files were modified by this hook"):
        tmp_repo.index.commit("fails")

    with pytest.raises(
        HookExecutionError,
        match="Please run 'git add test.py'",
    ):
        tmp_repo.index.commit("fails again")

    # once we add the changes, it will pass
    tmp_repo.git.add("test.py")
    tmp_repo.index.commit("succeeds")

    assert "test.ipynb" in tmp_repo.tree()
    assert "test.py" in tmp_repo.tree()
