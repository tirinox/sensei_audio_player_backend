import curses
import time


def choose_with_timeout(stdscr, options, timeout=10, default_index=0):
    """
    If timeout > 0:
      - show a countdown (updates every 0.05s) and auto‐select default when timer expires.
    If timeout <= 0:
      - do NOT display any timer line
      - switch to blocking getch() so the screen only redraws on keypress
      - wait indefinitely until Enter, Esc, or timeout logic (skipped) happens
    """
    curses.curs_set(0)

    input_buffer = ""
    filtered_options = options[:]
    current_selection = 0
    top_index = 0

    # If timeout <= 0, switch to blocking mode:
    if timeout <= 0:
        stdscr.nodelay(False)
    else:
        stdscr.nodelay(True)

    start_time = time.time()

    can_proceed = True

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # Header rows:
        #  - row 0: instructions
        #  - row 1: either countdown or blank
        #  - row 2: filter line
        header_rows = 3
        max_displayable = height - (header_rows + 1)

        # Re‐filter:
        filtered_options = [opt for opt in options if input_buffer.lower() in opt.lower()]
        if not filtered_options:
            filtered_options = ["<no matches>"]
            current_selection = 0
            can_proceed = False
        else:
            current_selection = min(current_selection, len(filtered_options) - 1)
            can_proceed = True

        # Adjust top_index so current_selection is visible:
        if current_selection < top_index:
            top_index = current_selection
        elif current_selection >= top_index + max_displayable:
            top_index = current_selection - max_displayable + 1

        # Draw instructions line:
        stdscr.addstr(0, 0, "Use ↑/↓ to move, type to filter, Enter to confirm (Esc to clear).")

        # Draw countdown only if timeout > 0:
        if timeout > 0:
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            # If timer expired, pick default:
            if remaining <= 0:
                # If there’s at least one match (not "<no matches>"), return its index.
                if filtered_options[0] != "<no matches>":
                    return options.index(filtered_options[0])
                else:
                    return default_index

            stdscr.addstr(1, 0, f"Auto‐selecting default in {remaining:2d} seconds")
        else:
            # leave row 1 blank (no timer)
            stdscr.move(1, 0)

        # Draw filter line (row 2):
        stdscr.addstr(2, 0, f"Filter: {input_buffer}")

        # Draw the visible slice of filtered_options starting at row 4:
        visible_slice = filtered_options[top_index : top_index + max_displayable]
        for idx, option in enumerate(visible_slice):
            screen_row = header_rows + 1 + idx  # i.e. row 4 + idx
            text = option[: width - 4]  # clip long strings
            if (top_index + idx) == current_selection:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(screen_row, 2, text)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(screen_row, 2, text)

        stdscr.refresh()

        # If timeout > 0, do non‐blocking getch() w/ short sleep to update countdown.
        # If timeout <= 0, this is blocking and only redraws on keypress.
        if timeout > 0:
            try:
                key = stdscr.getch()
            except Exception:
                key = -1
            # Small sleep so the countdown updates roughly every 0.05s
            time.sleep(0.05)
        else:
            key = stdscr.getch()

        # Handle keys:
        if key == curses.KEY_UP:
            if current_selection > 0:
                current_selection -= 1
        elif key == curses.KEY_DOWN:
            if current_selection < len(filtered_options) - 1:
                current_selection += 1
        elif key in (10, 13):  # Enter
            if can_proceed:
                return options.index(filtered_options[current_selection])
        elif key == 27:  # ESC clears filter
            input_buffer = ""
            current_selection = 0
            top_index = 0
        elif 32 <= key <= 126:  # Printable ASCII
            input_buffer += chr(key)
            current_selection = 0
            top_index = 0
        elif key in (8, 127):  # Backspace/Delete
            input_buffer = input_buffer[:-1]
            current_selection = 0
            top_index = 0
        # Otherwise, ignore and loop again


def run_menu(options, timeout=10, default_index=0):
    selected = curses.wrapper(choose_with_timeout, options, timeout, default_index)
    print(f"\nSelected: {options[selected]} (index {selected})")
    return selected
