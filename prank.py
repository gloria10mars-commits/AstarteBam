#!/usr/bin/env python3
"""
PRANK VIRUS - VERSION BLOAGUE
Attention : Ce script est une blague. Il ne fait rien de malveillant.
Le mot de passe est indiqué dans le titre de la fenêtre.
"""

import tkinter as tk
from tkinter import messagebox
import sys
import os

class PrankVirus:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🔒 ALERTE VIRUS - Mot de passe: 12345678")
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')
        
        # Empêcher la fermeture classique
        self.root.protocol("WM_DELETE_WINDOW", self.block_close)
        
        # Créer l'interface
        self.create_interface()
        
        # Bandeau rouge clignotant
        self.flash = False
        self.flash_alert()
        
    def create_interface(self):
        # Frame principal
        main_frame = tk.Frame(self.root, bg='black')
        main_frame.pack(expand=True, fill='both')
        
        # Titre effrayant
        title = tk.Label(
            main_frame,
            text="⚠️ VOTRE ORDINATEUR A ÉTÉ CRYPTÉ ⚠️",
            font=('Arial', 40, 'bold'),
            fg='red',
            bg='black'
        )
        title.pack(pady=30)
        
        # Message
        message = tk.Label(
            main_frame,
            text="Tous vos fichiers ont été chiffrés avec un algorithme AES-256.\n"
                 "Pour les récupérer, vous devez payer une rançon de 500€.\n\n"
                 "💰 Compte bancaire : FR76 1234 5678 9012 3456 7890 123\n"
                 "🏦 Banque : Banque Internationale\n\n"
                 "🔑 Entrez le mot de passe de déchiffrement ci-dessous :",
            font=('Arial', 16),
            fg='white',
            bg='black',
            justify='center'
        )
        message.pack(pady=20)
        
        # Champ de mot de passe
        self.password_entry = tk.Entry(
            main_frame,
            font=('Arial', 20),
            show='*',
            width=30,
            bg='#333',
            fg='white',
            insertbackground='white'
        )
        self.password_entry.pack(pady=20)
        self.password_entry.focus()
        self.password_entry.bind('<Return>', self.check_password)
        
        # Bouton de validation
        self.btn = tk.Button(
            main_frame,
            text="🔓 Décrypter",
            font=('Arial', 16, 'bold'),
            bg='red',
            fg='white',
            activebackground='darkred',
            activeforeground='white',
            command=self.check_password,
            width=20,
            height=2
        )
        self.btn.pack(pady=10)
        
        # Indice visible
        hint = tk.Label(
            main_frame,
            text="💡 Indice : Le mot de passe est dans le titre de la fenêtre !",
            font=('Arial', 12),
            fg='yellow',
            bg='black'
        )
        hint.pack(pady=20)
        
        # Compteur de tentatives
        self.attempts = 0
        self.attempt_label = tk.Label(
            main_frame,
            text="Tentatives : 0",
            font=('Arial', 12),
            fg='gray',
            bg='black'
        )
        self.attempt_label.pack(pady=10)
        
        # Footer "blague"
        footer = tk.Label(
            main_frame,
            text="MOt de passe incorrect \n"
                 "Réessayer!.",
            font=('Arial', 10),
            fg='#666',
            bg='black'
        )
        footer.pack(side='bottom', pady=20)
        
    def block_close(self):
        """Empêcher la fermeture de la fenêtre"""
        messagebox.showerror(
            "⛔ ACCÈS REFUSÉ",
            "Vous ne pouvez pas fermer cette fenêtre sans le mot de passe !\n\n"
            "💰 Payez la rançon ou entrez le mot de passe correct."
        )
    
    def flash_alert(self):
        """Faire clignoter un bandeau d'alerte"""
        # Créer un bandeau en haut si pas encore fait
        if not hasattr(self, 'alert_bar'):
            self.alert_bar = tk.Label(
                self.root,
                text="⚠️ ALERTE ! CRYPTAGE EN COURS ⚠️",
                font=('Arial', 14, 'bold'),
                fg='black',
                bg='red'
            )
            self.alert_bar.pack(side='top', fill='x')
        
        # Alterner les couleurs
        if self.flash:
            self.alert_bar.configure(bg='red', fg='black')
        else:
            self.alert_bar.configure(bg='darkred', fg='white')
        
        self.flash = not self.flash
        self.root.after(500, self.flash_alert)
    
    def check_password(self, event=None):
        """Vérifier le mot de passe"""
        password = self.password_entry.get()
        self.attempts += 1
        self.attempt_label.config(text=f"Tentatives : {self.attempts}")
        
        if password == "12345678":
            # Mot de passe correct - fermer
            messagebox.showinfo(
                "✅ DÉCRYPTAGE RÉUSSI",
                "Bravo ! Vous avez trouvé le mot de passe.\n\n"
                "Félicitations\n"
                "Pour la paye."
            )
            self.root.destroy()
            sys.exit(0)
        else:
            # Mot de passe incorrect
            messagebox.showerror(
                "❌ MOT DE PASSE INCORRECT",
                "Mot de passe erroné !\n\n"
                "💡 \n"
                " !"
            )
            self.password_entry.delete(0, tk.END)
            self.password_entry.focus()
            
            # Si trop de tentatives, ajouter un effet "effrayant"
            if self.attempts >= 5:
                self.root.configure(bg='red')
                tk.Label(
                    self.root,
                    text="⚠️ TROP DE TENTATIVES ! ⚠️",
                    font=('Arial', 30, 'bold'),
                    fg='white',
                    bg='red'
                ).pack(pady=10)
                self.root.after(1000, lambda: self.root.configure(bg='black'))

if __name__ == "__main__":
    # Vérifier si on est sous Linux avec X
    if os.name == 'posix' and 'DISPLAY' not in os.environ:
        print("⚠️ Ce script doit être exécuté dans un environnement graphique.")
        print("Sur le serveur via SSH, utilisez : DISPLAY=:0 python3 prank.py")
        sys.exit(1)
    
    try:
        app = PrankVirus()
        app.root.mainloop()
    except Exception as e:
        print(f"Erreur : {e}")
        print("Assurez-vous que tkinter est installé : sudo apt install python3-tk")
