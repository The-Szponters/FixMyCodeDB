from Loop import run_menu_loop

if __name__ == "__main__":
    try:
        run_menu_loop()
    except KeyboardInterrupt:
        print("\nExiting. Goodbye!")
