from template_fastcrud_api.contracts.greetings import Greeting
from template_fastcrud_api.core.contracts import Clock


def make_greeting(*, name: str, clock: Clock) -> Greeting:
    return Greeting(message=f"Hello, {name}!", generated_at=clock())
