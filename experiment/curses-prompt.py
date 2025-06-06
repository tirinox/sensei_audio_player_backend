import curses
import time


def choose_with_timeout(stdscr, options, timeout=10, default_index=0):
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(True)  # Make getch non-blocking
    current_selection = default_index
    start_time = time.time()

    while True:
        stdscr.clear()
        elapsed = int(time.time() - start_time)
        remaining = timeout - elapsed

        stdscr.addstr(0, 0, "Use ↑ ↓ to choose. Press Enter to confirm.")
        stdscr.addstr(1, 0, f"Auto-selecting default in {remaining} seconds...")

        for i, option in enumerate(options):
            if i == current_selection:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(3 + i, 2, option)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(3 + i, 2, option)

        stdscr.refresh()

        if remaining <= 0:
            return default_index

        try:
            key = stdscr.getch()
        except Exception:
            key = -1

        if key == curses.KEY_UP:
            current_selection = (current_selection - 1) % len(options)
        elif key == curses.KEY_DOWN:
            current_selection = (current_selection + 1) % len(options)
        elif key in (10, 13):  # Enter key
            return current_selection

        time.sleep(0.1)


def run_menu(options, timeout=10, default_index=0):
    selected = curses.wrapper(choose_with_timeout, options, timeout, default_index)
    print(f"\nSelected: {options[selected]} (index {selected})")
    return selected


# Example usage
if __name__ == "__main__":
    options = ["Option A", "Option B", "Option C"]
    run_menu(options, timeout=10, default_index=1)
