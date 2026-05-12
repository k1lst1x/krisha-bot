from messenger import KrishaMessenger


class _InvisibleLocator:
    def is_visible(self) -> bool:
        return False


class _FakePage:
    url = "https://krisha.kz/my/messages/?advertId=123#/"

    def locator(self, selector: str):  # noqa: ANN001
        return _InvisibleLocator()


class _EditorWithText:
    def is_visible(self) -> bool:
        return True

    def evaluate(self, script: str) -> str:  # noqa: ARG002
        return "DIV"

    def inner_text(self) -> str:
        return "Здравствуйте"


def test_verify_send_does_not_treat_chat_url_as_success_when_editor_still_has_text() -> None:
    messenger = KrishaMessenger()

    assert messenger._verify_send(_FakePage(), _EditorWithText(), expected_message="Здравствуйте") is False
