import csv
import json

def converti_database_csv(file_input, file_output):
    domande = []
    try:
        # Trova il separatore (, o ;)
        with open(file_input, 'r', encoding='utf-8', errors='ignore') as f:
            prima_riga = f.readline()
            separatore = ';' if ';' in prima_riga else ','
            
        with open(file_input, 'r', encoding='utf-8', errors='ignore') as f:
            lettore = csv.reader(f, delimiter=separatore, quotechar='"')
            contatore = 1
            
            for riga in lettore:
                if not riga or len(riga) < 8 or 'Domanda' in riga[1] or 'Item' in riga[0]:
                    continue
                    
                testo_domanda = riga[1].strip()
                lettere = ['a', 'b', 'c', 'd', 'e']
                opzioni_dict = {}
                
                # Popola le opzioni dinamicamente
                for i, lettera in enumerate(lettere):
                    testo_opt = riga[2+i].strip()
                    if testo_opt:
                        opzioni_dict[lettera] = testo_opt
                
                lettera_corretta = riga[7].strip().lower()
                testo_risposta = opzioni_dict.get(lettera_corretta, "")
                
                # Formato JSON esatto richiesto
                domande.append({
                    "numero": contatore,
                    "domanda": testo_domanda,
                    "opzioni": opzioni_dict,
                    "risposta_corretta": lettera_corretta,
                    "risposta": testo_risposta,
                    "id": contatore
                })
                contatore += 1
                    
        with open(file_output, 'w', encoding='utf-8') as f:
            json.dump(domande, f, indent=4, ensure_ascii=False)
            
        print(f"BINGO! Estratte {len(domande)} domande dal file CSV nel nuovo formato.")
        
    except Exception as e:
        print(f"Errore: {e}")

converti_database_csv('Domande-2-1.csv', 'domande2-1.json')