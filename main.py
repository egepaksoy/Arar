try:
    from local_dependencies import activate_local_dependencies
    activate_local_dependencies()
    from arar.offline import install_network_guard
    install_network_guard()
    from arar.app import main
except (ImportError, OSError) as exc:
    import sys
    text = ('Gerekli yerel Python bileşeni yüklenemedi: ' + str(exc) +
            '\n\nlibs klasörünü kontrol edin. Uyumlu Python sürümünü ve '
            'hazırlık adımlarını README_OFFLINE.md dosyasında bulabilirsiniz.')
    if sys.stderr is not None:
        print(text, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        pass
    else:
        try:
            root=tk.Tk()
            root.withdraw()
            messagebox.showerror('Arar • Eksik veya uyumsuz bileşen', text)
            root.destroy()
        except tk.TclError:
            pass
    raise SystemExit(1)

if __name__=='__main__':
    main()
