from arar.offline import install_network_guard

install_network_guard()

try:
    from arar.app import main
except ImportError as exc:
    import tkinter as tk
    from tkinter import messagebox
    root=tk.Tk()
    root.withdraw()
    messagebox.showerror('Arar • Eksik bileşen',
        'Gerekli yerel Python bileşeni bulunamadı: '+str(exc)+
        '\n\nBaşlat.bat ile açın veya requirements.txt bileşenlerini çevrimdışı kurun.')
    root.destroy()
    raise SystemExit(1)

if __name__=='__main__':
    main()
