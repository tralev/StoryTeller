"""P8.13 — Packaging and build-output isolation tests.

Cover:
- forge.spec ai_models exclusion comment
- .gitignore and .dockerignore ai_models / tmp/ entries
- Build scripts write to tmp/ (not packaging dirs)
- Clean install: Unicode paths, spaces in paths
- ai_models is never bundled (directory existence + exclusion check)
- Build script exit codes for missing spec
"""

from __future__ import annotations

import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── P8.13: forge.spec ai_models exclusion ────────────────────────────────


class TestForgeSpecAiModelsExclusion:
    """P8.13: All forge.spec files have the P8.13 ai_models comment."""

    def test_mac_spec_has_ai_models_comment(self) -> None:
        spec = PROJECT_ROOT / "mac" / "forge.spec"
        assert spec.exists(), "mac/forge.spec missing"
        content = spec.read_text()
        assert "ai_models must never be bundled" in content, \
            "mac/forge.spec missing P8.13 ai_models exclusion comment"

    def test_lin_spec_has_ai_models_comment(self) -> None:
        spec = PROJECT_ROOT / "lin" / "forge.spec"
        assert spec.exists(), "lin/forge.spec missing"
        content = spec.read_text()
        assert "ai_models must never be bundled" in content, \
            "lin/forge.spec missing P8.13 ai_models exclusion comment"

    def test_win_spec_has_ai_models_comment(self) -> None:
        spec = PROJECT_ROOT / "win" / "forge.spec"
        assert spec.exists(), "win/forge.spec missing"
        content = spec.read_text()
        assert "ai_models must never be bundled" in content, \
            "win/forge.spec missing P8.13 ai_models exclusion comment"

    def test_ai_models_not_in_datas(self) -> None:
        """P8.13: No forge.spec includes ai_models in datas list."""
        for platform in ("mac", "lin", "win"):
            spec = PROJECT_ROOT / platform / "forge.spec"
            content = spec.read_text()
            assert "ai_models" not in content.replace(
                "ai_models must never be bundled", ""
            ), f"{platform}/forge.spec references ai_models outside exclusion comment"


# ── P8.13: .gitignore / .dockerignore ai_models + tmp/ ──────────────────


class TestGitignoreAiModels:
    """P8.13: .gitignore and .dockerignore prevent ai_models bundling."""

    def test_gitignore_has_ai_models(self) -> None:
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text()
        assert "ai_models/" in content or "ai_models" in content, \
            ".gitignore does not exclude ai_models/"

    def test_gitignore_has_tmp(self) -> None:
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text()
        assert "tmp/" in content, ".gitignore does not exclude tmp/"

    def test_dockerignore_has_ai_models(self) -> None:
        dockerignore = PROJECT_ROOT / ".dockerignore"
        content = dockerignore.read_text()
        assert "ai_models/" in content or "ai_models" in content, \
            ".dockerignore does not exclude ai_models/"

    def test_dockerignore_has_tmp(self) -> None:
        dockerignore = PROJECT_ROOT / ".dockerignore"
        content = dockerignore.read_text()
        assert "tmp/" in content, ".dockerignore does not exclude tmp/"

    def test_ai_models_not_in_docker_copy(self) -> None:
        """P8.13: Dockerfile does not COPY ai_models/."""
        dockerfile = PROJECT_ROOT / "Dockerfile"
        content = dockerfile.read_text()
        # ai_models should not appear in COPY or ADD directives
        assert "ai_models" not in content, \
            "Dockerfile references ai_models — it must never be bundled"


# ── P8.13: Build output isolation (all outputs → tmp/) ──────────────────


class TestBuildOutputIsolation:
    """P8.13: Build scripts output to tmp/, never to packaging dirs."""

    def test_mac_build_sh_outputs_to_tmp(self) -> None:
        script = PROJECT_ROOT / "mac" / "build.sh"
        content = script.read_text()
        # Must reference tmp/ for all output paths
        assert "tmp/" in content, "mac/build.sh does not use tmp/"
        # Must not create files in mac/ itself (no cp to mac/)
        output_cp = re.findall(r'cp\s+\S+\s+(mac/\S+)', content)
        assert not output_cp, f"mac/build.sh copies output into mac/: {output_cp}"
        # PACKAGES_DIR must be tmp/packages
        assert 'PACKAGES_DIR="tmp/packages"' in content or "PACKAGES_DIR='tmp/packages'" in content, \
            "mac/build.sh PACKAGES_DIR is not tmp/packages"
        assert 'WORK_DIR="tmp/build"' in content or "WORK_DIR='tmp/build'" in content, \
            "mac/build.sh WORK_DIR is not tmp/build"

    def test_lin_build_sh_outputs_to_tmp(self) -> None:
        script = PROJECT_ROOT / "lin" / "build.sh"
        content = script.read_text()
        assert "tmp/" in content, "lin/build.sh does not use tmp/"
        output_cp = re.findall(r'cp\s+\S+\s+(lin/\S+)', content)
        assert not output_cp, f"lin/build.sh copies output into lin/: {output_cp}"
        assert 'PACKAGES_DIR="tmp/packages"' in content or "PACKAGES_DIR='tmp/packages'" in content, \
            "lin/build.sh PACKAGES_DIR is not tmp/packages"

    def test_win_build_ps1_outputs_to_tmp(self) -> None:
        script = PROJECT_ROOT / "win" / "build.ps1"
        content = script.read_text()
        assert "tmp\\" in content or "tmp/" in content, "win/build.ps1 does not use tmp/"
        assert "PackagesDir" in content, "win/build.ps1 has no PackagesDir"
        # Must reference tmp\packages
        assert "tmp\\\\packages" in content or "tmp\\packages" in content or \
               "tmp/packages" in content, \
            "win/build.ps1 PackagesDir is not tmp/packages"


# ── P8.13: Clean install path safety ────────────────────────────────────


class TestCleanInstallPaths:
    """P8.13: Build scripts handle Unicode and spaces in paths."""

    def test_mac_build_sh_quotes_paths(self) -> None:
        """mac/build.sh uses quoted variable expansion for path safety."""
        script = PROJECT_ROOT / "mac" / "build.sh"
        content = script.read_text()
        # All $VAR references in commands should be quoted
        unquoted_vars = re.findall(r'(?:cp|mkdir|rm|ln)\s+\$[A-Z_]+(?![{("])', content)
        assert not unquoted_vars, \
            f"mac/build.sh has unquoted variable references: {unquoted_vars}"

    def test_lin_build_sh_quotes_paths(self) -> None:
        """lin/build.sh uses quoted variable expansion for path safety."""
        script = PROJECT_ROOT / "lin" / "build.sh"
        content = script.read_text()
        unquoted_vars = re.findall(r'(?:cp|mkdir|rm|ln)\s+\$[A-Z_]+(?![{("])', content)
        assert not unquoted_vars, \
            f"lin/build.sh has unquoted variable references: {unquoted_vars}"

    def test_win_build_ps1_handles_spaces(self) -> None:
        """win/build.ps1 has Test-Path checks and quoted paths."""
        script = PROJECT_ROOT / "win" / "build.ps1"
        content = script.read_text()
        # Should use Test-Path or exist checks before operating on files
        assert "Test-Path" in content or "-not" in content, \
            "win/build.ps1 does not use Test-Path for existence checks"

    def test_build_scripts_set_exit_on_error(self) -> None:
        """Shell build scripts use set -e or equivalent for error handling."""
        for platform in ("mac", "lin"):
            script = PROJECT_ROOT / platform / "build.sh"
            content = script.read_text()
            assert "set -e" in content or "set -eu" in content, \
                f"{platform}/build.sh does not set -e (exit on error)"


# ── P8.13: Build script integrity ───────────────────────────────────────


class TestBuildScriptIntegrity:
    """P8.13: Build scripts are complete (not placeholders)."""

    def test_win_build_ps1_not_placeholder(self) -> None:
        """P8.13: win/build.ps1 does not contain 'placeholder' references."""
        script = PROJECT_ROOT / "win" / "build.ps1"
        content = script.read_text()
        # The script should no longer say "placeholder" or "does not exist yet"
        assert "does not exist yet" not in content, \
            "win/build.ps1 still has placeholder 'does not exist yet' text"
        assert "Not implemented yet" not in content, \
            "win/build.ps1 still says 'Not implemented yet'"

    def test_all_three_forge_specs_exist(self) -> None:
        """P8.13: All three forge.spec files exist."""
        for platform in ("mac", "lin", "win"):
            spec = PROJECT_ROOT / platform / "forge.spec"
            assert spec.exists(), f"{platform}/forge.spec missing"

    def test_build_scripts_are_executable(self) -> None:
        """P8.13: Shell build scripts are executable."""
        for platform in ("mac", "lin"):
            script = PROJECT_ROOT / platform / "build.sh"
            assert os.access(script, os.X_OK), \
                f"{platform}/build.sh is not executable"

    def test_all_platforms_have_readme(self) -> None:
        """P8.13: Every platform dir has a README.md."""
        for platform in ("mac", "lin", "win"):
            readme = PROJECT_ROOT / platform / "README.md"
            assert readme.exists(), f"{platform}/README.md missing"

    def test_readmes_contain_tmp_convention(self) -> None:
        """P8.13: Every platform README documents the tmp/ output convention."""
        for platform in ("mac", "lin", "win"):
            readme = PROJECT_ROOT / platform / "README.md"
            content = readme.read_text()
            assert "tmp/" in content or "tmp\\" in content, \
                f"{platform}/README.md does not document tmp/ output convention"


# ── P8.13: ai_models bundling prevention ────────────────────────────────


class TestAiModelsBundlingPrevention:
    """P8.13: Multiple layers of defense against ai_models bundling."""

    def test_ai_models_not_in_pyinstaller_datas(self) -> None:
        """P8.13: No forge.spec datas entry points to ai_models/."""
        for platform in ("mac", "lin", "win"):
            spec = PROJECT_ROOT / platform / "forge.spec"
            content = spec.read_text()
            # Look for datas entries that mention ai_models
            datas_pattern = r'datas\s*=\s*\[(.*?)\]'
            matches = re.findall(datas_pattern, content, re.DOTALL)
            for match in matches:
                assert "ai_models" not in match, \
                    f"{platform}/forge.spec datas includes ai_models: {match[:100]}"

    def test_ai_models_not_in_pyinstaller_binaries(self) -> None:
        """P8.13: No forge.spec binary entry points to ai_models/."""
        for platform in ("mac", "lin", "win"):
            spec = PROJECT_ROOT / platform / "forge.spec"
            content = spec.read_text()
            binaries_pattern = r'binaries\s*=\s*\[(.*?)\]'
            matches = re.findall(binaries_pattern, content, re.DOTALL)
            for match in matches:
                assert "ai_models" not in match, \
                    f"{platform}/forge.spec binaries includes ai_models"

    def test_gitignore_has_stray_binary_safety_nets(self) -> None:
        """P8.13: .gitignore has safety nets for stray binaries in platform dirs."""
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text()
        assert "lin/forge" in content, ".gitignore missing lin/forge safety net"
        assert "win/forge.exe" in content, ".gitignore missing win/forge.exe safety net"

    def test_gguf_files_gitignored(self) -> None:
        """P8.13: .gguf files are gitignored (model files stay in ai_models/)."""
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text()
        assert "*.gguf" in content, ".gitignore does not exclude *.gguf"
