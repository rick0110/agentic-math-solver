import base64
import os
import zipfile
from pathlib import Path

def process_uploaded_files(files_data: list[dict], output_dir: Path) -> str:
    if not files_data:
        return ""
    
    uploads_dir = output_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    extracted_texts = []
    
    for f in files_data:
        name = f.get("name", "unknown")
        b64data = f.get("data", "")
        if "," in b64data:
            b64data = b64data.split(",")[1]
            
        file_path = uploads_dir / name
        try:
            with open(file_path, "wb") as out_f:
                out_f.write(base64.b64decode(b64data))
        except Exception as e:
            extracted_texts.append(f"Failed to decode file {name}: {e}")
            continue

        ext = file_path.suffix.lower()
        if ext == ".zip":
            try:
                with zipfile.ZipFile(file_path, 'r') as z:
                    file_list = z.namelist()
                    extracted_texts.append(f"--- Arquivo ZIP: {name} ---\nConteúdo (arquivos): {', '.join(file_list)}")
            except Exception as e:
                extracted_texts.append(f"Falha ao ler ZIP {name}: {e}")
        elif ext in [".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css"]:
            try:
                content = file_path.read_text(encoding="utf-8")
                extracted_texts.append(f"--- Arquivo: {name} ---\n{content}")
            except Exception as e:
                extracted_texts.append(f"Falha ao ler {name}: {e}")
        else:
            extracted_texts.append(f"--- Arquivo: {name} ---\n(Salvo em {file_path}, formato não extraído automaticamente. Agentes podem usar python para abrir este arquivo.)")
            
    if not extracted_texts:
        return ""
        
    return "\n\nArquivos Anexados (Pré-processamento):\n" + "\n\n".join(extracted_texts) + "\n\n"
