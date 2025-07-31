import tkinter as tk
from screens.login_screen import LoginScreen

def main():
    root = tk.Tk()
    root.title("Chama Admin Desktop App")
    root.geometry("400x300")
    app = LoginScreen(root)
    root.mainloop()

if __name__ == "__main__":
    main()
