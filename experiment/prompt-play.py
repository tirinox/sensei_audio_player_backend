from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.application.current import get_app_or_none
from asyncio import TimeoutError, wait_for, run
import asyncio


async def get_user_choice(options, timeout=10, default_index=0):
    """
    Prompt user to select from options, with timeout fallback to default.

    Args:
        options (list): Options to display.
        timeout (int): Timeout in seconds.
        default_index (int): Default choice index.

    Returns:
        int: Selected option index.
    """
    assert 0 <= default_index < len(options), "Invalid default index"

    print("Choose an option by number (0 to {}):".format(len(options) - 1))
    for i, option in enumerate(options):
        print(f"  {i}: {option}")

    session = PromptSession()

    async def read_input():
        return await session.prompt_async("> ")

    try:
        with patch_stdout():
            user_input = await wait_for(read_input(), timeout=timeout)
            if user_input.isdigit():
                idx = int(user_input)
                if 0 <= idx < len(options):
                    print(f"Selected: {options[idx]} (index {idx})")
                    return idx
            print("Invalid input. Using default.")
    except (TimeoutError, EOFError, KeyboardInterrupt):
        print(f"\nTimed out. Defaulting to: {options[default_index]} (index {default_index})")

    return default_index


# Example usage
if __name__ == "__main__":
    options = ["Red", "Green", "Blue"]
    asyncio.run(get_user_choice(options, timeout=10, default_index=2))