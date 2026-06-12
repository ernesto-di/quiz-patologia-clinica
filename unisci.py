import json

# Definizione dei file di input e di output
file_1 = "quiz2.json"
file_2 = "quiz2-1.json"
file_finale = "quiz_completo.json"

def unisci_database():
    try:
        # 1. Carica il primo file JSON
        print(f"Caricamento di {file_1}...")
        with open(file_1, 'r', encoding='utf-8') as f:
            dati_1 = json.load(f)
        
        # 2. Carica il secondo file JSON
        print(f"Caricamento di {file_2}...")
        with open(file_2, 'r', encoding='utf-8') as f:
            dati_2 = json.load(f)
            
        # 3. Unisci le due liste di domande
        tutte_le_domande = dati_1 + dati_2
        
        print("Riordinamento degli ID e dei numeri in corso...")
        # 4. Corregge i numeri e gli ID rendendoli sequenziali (1, 2, 3... fino alla fine)
        for indice, domanda in enumerate(tutte_le_domande, start=1):
            domanda['numero'] = indice
            domanda['id'] = indice
            
        # 5. Salva il super-file unito
        with open(file_finale, 'w', encoding='utf-8') as f:
            json.dump(tutte_le_domande, f, indent=4, ensure_ascii=False)
            
        print(f"\n🎉 SUCCESSO! I file sono stati fusi insieme.")
        print(f"Totale domande nel nuovo file '{file_finale}': {len(tutte_le_domande)}")
        
    except FileNotFoundError as e:
        print(f"\n❌ Errore: Uno dei file non è stato trovato nella cartella. Dettaglio: {e}")
    except json.JSONDecodeError as e:
        print(f"\n❌ Errore di sintassi nel file JSON (parentesi o virgole mancanti): {e}")

# Avvia l'unione
unisci_database()