import pytest
from pydantic import ValidationError

from nexo.core.models import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    DataClass,
    InvalidTransition,
    RiskLevel,
    VerificationStatus,
)


def make(**kw):
    base = dict(
        tool="fs.write",
        risk_level=RiskLevel.MODIFIES_FILES,
        expected_outcome="archivo creado",
        verifier="file_exists",
    )
    base.update(kw)
    return ActionRequest(**base)


def test_defaults_are_restrictive():
    a = make()
    assert a.data_class == DataClass.LOCAL
    assert a.from_untrusted_content is False
    assert a.status == ActionStatus.PROPOSED


def test_risky_action_requires_verifier():
    with pytest.raises(ValidationError):
        make(verifier=None)


def test_info_action_can_skip_verifier():
    assert make(risk_level=RiskLevel.INFO, verifier=None).verifier is None


def test_happy_path_transitions():
    a = make()
    for s in (ActionStatus.APPROVED, ActionStatus.RUNNING, ActionStatus.SUCCEEDED):
        a.transition(s)
    assert a.status == ActionStatus.SUCCEEDED


def test_cannot_skip_approval():
    a = make()
    with pytest.raises(InvalidTransition):
        a.transition(ActionStatus.RUNNING)


def test_denied_is_terminal():
    a = make()
    a.transition(ActionStatus.DENIED)
    with pytest.raises(InvalidTransition):
        a.transition(ActionStatus.APPROVED)


def test_done_requires_verification():
    ok = ActionResult(action_id="x", status=ActionStatus.SUCCEEDED)
    assert not ok.can_report_done()  # tuvo éxito pero sin verificar
    ok.verification = VerificationStatus.VERIFIED
    assert ok.can_report_done()
    failed = ActionResult(
        action_id="x", status=ActionStatus.FAILED, verification=VerificationStatus.VERIFIED
    )
    assert not failed.can_report_done()
