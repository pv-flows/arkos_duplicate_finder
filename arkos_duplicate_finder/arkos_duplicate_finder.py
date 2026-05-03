import os
import hashlib
import json
import csv
import re
import zipfile
import traceback
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Detecta automaticamente a pasta onde o executável (ou script) está rodando.
# Funciona tanto como .py quanto como .exe compilado com PyInstaller.
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Rodando como .exe gerado pelo PyInstaller
    BASE_DIR = Path(sys.executable).parent
else:
    # Rodando como script .py normal
    BASE_DIR = Path(__file__).parent

ROMS_DIR       = BASE_DIR                      # Varredura começa na pasta do executável
REPORT_DIR     = BASE_DIR                      # Relatórios salvos na mesma pasta
QUARENTENA_DIR = BASE_DIR / "QUARENTENA_ROMS"  # Subpasta de quarentena

# Tamanho do chunk para hash parcial (64 KB)
PARTIAL_HASH_SIZE = 64 * 1024

# Expressão regular para limpar tags regionais e de versão
TAGS_REGEX = re.compile(r'\s*\(.*?\)\s*|\s*\[.*?\]\s*')

# Extensões comuns de grandes arquivos
LARGE_FILE_EXTS = {'.iso', '.chd', '.pbp', '.cso', '.bin', '.img', '.cdi'}

def get_hashes(filepath, file_size):
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    
    try:
        with open(filepath, 'rb') as f:
            if file_size > 50 * 1024 * 1024 and filepath.suffix.lower() in LARGE_FILE_EXTS:
                first_chunk = f.read(PARTIAL_HASH_SIZE)
                f.seek(-min(PARTIAL_HASH_SIZE, file_size), os.SEEK_END)
                last_chunk = f.read(PARTIAL_HASH_SIZE)
                
                md5.update(first_chunk + last_chunk)
                sha1.update(first_chunk + last_chunk)
                return md5.hexdigest(), sha1.hexdigest(), True
            else:
                while chunk := f.read(8192):
                    md5.update(chunk)
                    sha1.update(chunk)
                return md5.hexdigest(), sha1.hexdigest(), False
    except Exception:
        return None, None, False

def get_zip_content_hash(filepath):
    if not zipfile.is_zipfile(filepath):
        return None
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            infos = sorted([(info.filename, info.file_size) for info in z.infolist()])
            content_str = str(infos).encode('utf-8')
            return hashlib.md5(content_str).hexdigest()
    except Exception:
        return None

def normalize_name(filename):
    base = Path(filename).stem
    clean = TAGS_REGEX.sub('', base).strip().lower()
    return clean

def scan_roms():
    print(f"[*] Iniciando varredura em: {ROMS_DIR.resolve()}")
    
    roms_path = Path(ROMS_DIR)
    if not roms_path.exists():
        print(f"\n[AVISO] A pasta {ROMS_DIR.resolve()} NÃO foi encontrada!")
        return []

    print("[*] Lendo a estrutura enorme de pastas... aguarde.\n")
    
    roms_data = []
    
    # Lista completamente atualizada e filtrada contra sistema
    supported_systems = [
        '3do', 'advision', 'alg', 'amiga', 'amigacd32', 'amstradcpc', 'apple2', 'arcade', 
        'arduboy', 'astrocde', 'atari800', 'atari2600', 'atari5200', 'atari7800', 
        'atarijaguar', 'atarilynx', 'atarist', 'atarixegs', 'atomiswave', 'c16', 'c64', 
        'c128', 'channelf', 'coco3', 'coleco', 'cps1', 'cps2', 'cps3', 'doom', 'dos', 
        'dreamcast', 'easyrpg', 'enterprise', 'famicom', 'fbneo', 'fds', 'gameandwatch', 
        'gamegear', 'gb', 'gba', 'gbc', 'genesis', 'gx4000', 'intellivision', 'j2me', 
        'love2d', 'lowresnx', 'mame', 'mame2003', 'mastersystem', 'megadrive', 'megaduck', 
        'msumd', 'msx', 'msx2', 'mv', 'n64', 'n64dd', 'naomi', 'nds', 'neogeo', 'neogeocd', 
        'nes', 'ngp', 'ngpc', 'odyssey2', 'onscripter', 'openbor', 'palm', 'pc98', 'pcengine', 
        'pcenginecd', 'pcfx', 'pico', 'pico-8', 'piece', 'pokemonmini', 'psp', 'pspminis', 
        'psx', 'satellaview', 'saturn', 'scummvm', 'scv', 'sega32x', 'segacd', 'sfc', 
        'sg-1000', 'sgb', 'snes', 'snes-hacks', 'snesmsu1', 'solarus', 'sufami', 'supergrafx', 
        'supervision', 'thomson', 'ti99', 'tic80', 'turbografx', 'turbografxcd', 'tvc', 
        'uzebox', 'vectrex', 'vic20', 'virtualboy', 'vmac', 'vmu', 'wasm4', 'wolf', 
        'wonderswan', 'wonderswancolor', 'x1', 'x68000', 'zx81', 'zxspectrum'
    ]
    
    for system in supported_systems:
        system_path = roms_path / system
        if not system_path.exists():
            continue
            
        files = [f for f in system_path.rglob('*') if f.is_file() and not f.name.startswith('.')]
        total_files = len(files)
        
        if total_files == 0:
            continue
            
        print(f"Sistema: {system.upper()} ({total_files} arquivos encontrados)")
        
        for idx, file_path in enumerate(files):
            if file_path.suffix.lower() not in ['.xml', '.txt', '.jpg', '.png', '.state', '.srm']:
                size = file_path.stat().st_size
                if size > 0:
                    md5_hash, sha1_hash, is_partial = get_hashes(file_path, size)
                    norm_name = normalize_name(file_path.name)
                    zip_hash = get_zip_content_hash(file_path) if file_path.suffix.lower() == '.zip' else None
                    
                    roms_data.append({
                        'system': system,
                        'path': str(file_path),
                        'filename': file_path.name,
                        'size': size,
                        'norm_name': norm_name,
                        'md5': md5_hash,
                        'sha1': sha1_hash,
                        'is_partial': is_partial,
                        'zip_hash': zip_hash
                    })
            
            percent = (idx + 1) / total_files
            bar_length = 30
            filled = int(bar_length * percent)
            bar = '█' * filled + '-' * (bar_length - filled)
            
            sys.stdout.write(f"\r   [{bar}] {percent:.0%} ({idx+1}/{total_files}) processados")
            sys.stdout.flush()
            
        print("\n")

    return roms_data

def find_duplicates(roms_data):
    duplicates = {
        'exact': defaultdict(list),    
        'partial': defaultdict(list),  
        'zip': defaultdict(list),      
        'name_size': defaultdict(list),
        'regional': defaultdict(list)  
    }
    
    if not roms_data:
        return duplicates
        
    exact_g = defaultdict(list)
    partial_g = defaultdict(list)
    zip_g = defaultdict(list)
    ns_g = defaultdict(list)
    reg_g = defaultdict(list)
    
    for rom in roms_data:
        if not rom['is_partial'] and rom['md5']: exact_g[rom['md5']].append(rom)
        if rom['is_partial'] and rom['md5']: partial_g[rom['md5']].append(rom)
        if rom['zip_hash']: zip_g[rom['zip_hash']].append(rom)
        ns_g[f"{rom['system']}_{rom['norm_name']}_{rom['size']}"].append(rom)
        reg_g[f"{rom['system']}_{rom['norm_name']}"].append(rom)
        
    for k, v in exact_g.items(): 
        if len(v) > 1: duplicates['exact'][k] = v
    for k, v in partial_g.items(): 
        if len(v) > 1: duplicates['partial'][k] = v
    for k, v in zip_g.items(): 
        if len(v) > 1: duplicates['zip'][k] = v
    for k, v in ns_g.items(): 
        if len(v) > 1: duplicates['name_size'][k] = v
    for k, v in reg_g.items(): 
        if len(v) > 1: duplicates['regional'][k] = v
        
    return duplicates

def generate_reports(duplicates, rom_count):
    if rom_count == 0:
        return
        
    print(f"[*] Analisando duplicatas e escrevendo relatórios em: {REPORT_DIR.resolve()}...\n")
    
    total_wasted_space = 0
    all_dupes_list = []
    processed_paths = set()
    
    txt_path = REPORT_DIR / 'r36s_relatorio_duplicatas.txt'
    csv_path = REPORT_DIR / 'r36s_relatorio_duplicatas.csv'
    json_path = REPORT_DIR / 'r36s_relatorio_duplicatas.json'
    
    with open(txt_path, 'w', encoding='utf-8') as f_txt:
        f_txt.write("========================================================\n")
        f_txt.write("  RELATÓRIO DE CÓPIAS E DUPLICATAS R36S (ARKOS)\n")
        f_txt.write("========================================================\n")
        f_txt.write("AVISO LEGAL: SCRIPT DE MAPEAMENTO GERADO AUTOMATICAMENTE.\n\n")
        
        categories = [
            ('exact', '🔴 CÓPIAS EXATAS (Mesmo arquivo, ignorando nome)'),
            ('partial', '🔴 CÓPIAS EXATAS DE CD/ISO (PSX/PSP/DC)'),
            ('zip', '🟠 ZIPS COM MESMO CONTEÚDO ROM (Arcade/NeoGeo)'),
            ('name_size', '🟡 ARQUIVOS COM MESMO NOME BASE E TAMANHO (Alta suspeita)'),
            ('regional', '🔵 VERSÕES REGIONAIS/HACKS (Mesmo jogo, edições diferentes)')
        ]
        
        for cat_key, cat_name in categories:
            f_txt.write(f"\n[ {cat_name} ]\n")
            f_txt.write("-" * 60 + "\n")
            
            group = duplicates[cat_key]
            if not group:
                f_txt.write("Tudo limpo nesta categoria!\n")
                continue
                
            for hash_key, roms in group.items():
                f_txt.write(f"\n>> Grupo encontrado no console - {roms[0]['system'].upper()}:\n")
                
                for i, rom in enumerate(roms):
                    is_dupe = "[MANTER?]" if i == 0 else "[CÓPIA]"
                    
                    if rom['path'] not in processed_paths:
                        if i > 0: total_wasted_space += rom['size']
                        
                        all_dupes_list.append({
                            'Categoria Operacional': cat_name,
                            'Sistema': rom['system'],
                            'Jogo (Limpo)': rom['norm_name'],
                            'Nome do Arquivo': rom['filename'],
                            'Status Sugerido': 'Manter' if i == 0 else 'Cópia/Extra',
                            'Tamanho (MB)': round(rom['size'] / (1024*1024), 2),
                            'Caminho Completo': rom['path']
                        })
                        processed_paths.add(rom['path'])
                        
                    f_txt.write(f" {is_dupe} {rom['filename']} | {round(rom['size']/1024/1024, 2)} MB\n")
                    f_txt.write(f"     └─ {rom['path']}\n")

    if all_dupes_list:
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f_csv:
            writer = csv.DictWriter(f_csv, fieldnames=all_dupes_list[0].keys(), delimiter=';')
            writer.writeheader()
            writer.writerows(all_dupes_list)

    with open(json_path, 'w', encoding='utf-8') as f_json:
        json.dump(duplicates, f_json, indent=4, ensure_ascii=False)
        
    print(f"[!] PROCESSAMENTO DE AVALIAÇÃO CONCLUÍDO!")
    print(f"[!] Espaço físico ocupado pelas cópias totais: {round(total_wasted_space / (1024*1024*1024), 2)} GB\n")

def move_safeduplicates_to_quarantine(duplicates):
    print("="*60)
    print("  OPERAÇÃO DE QUARENTENA")
    print("="*60)
    print("O sistema isolará apenas as duplicatas EXATAS (100% iguais)")
    print("e os ZIPs redundantes. Arquivos parecidos, de regiões")
    print("diferentes, continuarão intocados por segurança.\n")
    
    resposta = input(f"Deseja isolar as cópias exatas em {QUARENTENA_DIR.resolve()}? (S/N): ").strip().lower()
    
    if resposta == 's':
        quarentena_path = QUARENTENA_DIR
        if not quarentena_path.exists():
            quarentena_path.mkdir(parents=True, exist_ok=True)
            
        moved_count = 0
        moved_size = 0
        processed_paths = set()
        
        # Categorias restritas e ultra-seguras para deletar/mover
        safe_categories = ['exact', 'partial', 'zip']
        
        for cat in safe_categories:
            for hash_key, roms in duplicates[cat].items():
                
                # Ignoramos o índice 0 (é o arquivo que vamos manter na pasta do jogo)
                for i in range(1, len(roms)):
                    rom_path = Path(roms[i]['path'])
                    
                    if str(rom_path) in processed_paths:
                        continue
                        
                    if rom_path.exists():
                        # Cria espelho do console na quarentena (ex: QUARENTENA/gba/)
                        sys_dir = quarentena_path / roms[i]['system']
                        if not sys_dir.exists():
                            sys_dir.mkdir(parents=True, exist_ok=True)
                            
                        # Mover de fato
                        dest_path = sys_dir / roms[i]['filename']
                        
                        # Prevenção rara: se já houver arquivo com mesmo nome na quarentena
                        if dest_path.exists():
                            dest_path = sys_dir / f"{rom_path.stem}_copia_extra{rom_path.suffix}"
                            
                        try:
                            shutil.move(str(rom_path), str(dest_path))
                            moved_count += 1
                            moved_size += roms[i]['size']
                            processed_paths.add(str(rom_path))
                            print(f" -> Movido: {roms[i]['filename']} ({roms[i]['system']})")
                        except Exception as e:
                            print(f" -> ERRO ao mover {roms[i]['filename']}: {e}")

        print(f"\n[!] LIMPEZA CONCLUÍDA!")
        print(f"[!] {moved_count} arquivos isolados com segurança.")
        print(f"[!] {round(moved_size/(1024*1024), 2)} MB liberados nas pastas de consoles.")
    else:
        print("\n[!] Operação cancelada. Nenhum arquivo foi movido.")


if __name__ == "__main__":
    try:
        print("=========================================")
        print("   R36S DUPLICATE FINDER v1.0 (ARKOS)    ")
        print("=========================================\n")
        
        data = scan_roms()
        
        if len(data) == 0:
            print("\n[!] Nenhum jogo encontrado. Verifique se o pendrive/SD está inserido e a letra está certa.")
        else:
            dupes = find_duplicates(data)
            generate_reports(dupes, len(data))
            
            # Chama a nova etapa no final
            move_safeduplicates_to_quarantine(dupes)
            
    except Exception as e:
        print("\n\n[ERRO CRÍTICO] O aplicativo encontrou um erro no processo:")
        traceback.print_exc()
        
    finally:
        input("\n\nPressione qualquer tecla para encerrar / fechar...")
