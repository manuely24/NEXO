from nexo.tools.base import ToolRegistry
from nexo.tutor.english import EnglishCorrectTextTool, EnglishExplainGrammarTool


def test_corrects_common_a2_b1_mistakes_offline():
    result = EnglishCorrectTextTool().run({"text": "I am agree. She go to class."})

    assert "I agree" in result
    assert "She goes" in result
    assert "A2.4/B1" in result


def test_explains_supported_grammar_topic():
    result = EnglishExplainGrammarTool().run({"topic": "present simple"})

    assert "does" in result
    assert "A2.4/B1" in result


def test_tutor_tools_are_registered_without_cloud_access():
    registry = ToolRegistry()
    registry.register(EnglishCorrectTextTool())
    registry.register(EnglishExplainGrammarTool())

    assert registry.names() == ("english.correct_text", "english.explain_grammar")