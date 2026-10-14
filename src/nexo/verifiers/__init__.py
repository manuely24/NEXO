"""Verificadores de efectos observables."""

from nexo.verifiers.base import Verification, Verifier, VerifierRegistry
from nexo.verifiers.file_verifiers import FileContainsVerifier, FileExistsVerifier
from nexo.verifiers.git_verifier import GitStatusVerifier
from nexo.verifiers.output_verifiers import (
    AcademicImportVerifier,
    AcademicTaskExistsVerifier,
    JsonListVerifier,
    JsonObjectVerifier,
)
from nexo.verifiers.project_verifier import ProjectScaffoldVerifier

__all__ = [
    "FileContainsVerifier",
    "FileExistsVerifier",
    "GitStatusVerifier",
    "AcademicTaskExistsVerifier",
    "AcademicImportVerifier",
    "JsonListVerifier",
    "JsonObjectVerifier",
    "ProjectScaffoldVerifier",
    "Verification",
    "Verifier",
    "VerifierRegistry",
]