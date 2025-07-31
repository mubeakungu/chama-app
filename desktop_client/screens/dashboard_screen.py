import tkinter as tk
from utils.api import fetch_dashboard_data

def open_dashboard(master):
    frame = tk.Frame(master)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Dashboard", font=("Arial", 16)).pack(pady=10)

    data = fetch_dashboard_data()
    if not data:
        tk.Label(frame, text="Failed to load dashboard").pack()
        return

    members = data.get("members", [])
    loans = data.get("loans", [])

    tk.Label(frame, text="Total Contributions:").pack()
    for m in members:
        tk.Label(frame, text=f"{m[0]} - KES {m[1]}").pack()

    tk.Label(frame, text="\nLoan Summary:").pack()
    for l in loans:
        tk.Label(frame, text=f"{l[0]} | Loan: {l[1]} | Repaid: {l[3]} | Balance: {l[4]}").pack()

    tk.Button(frame, text="Logout", command=lambda: restart(master)).pack(pady=10)

def restart(master):
    master.destroy()
    import main
    main.main()
