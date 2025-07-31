import tkinter as tk
from tkinter import messagebox
from utils.api import login_admin
from screens.dashboard_screen import open_dashboard

class LoginScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.pack()

        tk.Label(self, text="Admin Login", font=("Arial", 16)).pack(pady=10)
        tk.Label(self, text="Username").pack()
        self.username_entry = tk.Entry(self)
        self.username_entry.pack()

        tk.Label(self, text="Password").pack()
        self.password_entry = tk.Entry(self, show="*")
        self.password_entry.pack()

        tk.Button(self, text="Login", command=self.login).pack(pady=10)

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        success = login_admin(username, password)
        if success:
            self.destroy()
            open_dashboard(self.master)
        else:
            messagebox.showerror("Login Failed", "Invalid credentials")
