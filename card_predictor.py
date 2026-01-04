# card_predictor.py - VERSION CORRIGÉE ET STABILISÉE

import re
import logging
import time
import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict, deque
import pytz
import unicodedata

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ================== CONFIG ==================
BENIN_TZ = pytz.timezone("Africa/Porto-Novo")

# --- 1. RÈGLES STATIQUES (13 Règles Exactes) ---
STATIC_RULES = {
    "10♦️": "♠️", "10♠️": "❤️", 
    "9♣️": "❤️", "9♦️": "♠️",
    "8♣️": "♠️", "8♠️": "♣️", 
    "7♠️": "♠️", "7♣️": "♣️",
    "6♦️": "♣️", "6♣️": "♦️", 
    "A❤️": "❤️", 
    "5❤️": "❤️", "5♠️": "♠️"
}

# Symboles pour les status de vérification
SYMBOL_MAP = {0: '✅0️⃣', 1: '✅1️⃣', 2: '✅2️⃣', 'lost': '❌'}

# Sessions de prédictions
PREDICTION_SESSIONS = [(1, 6), (9, 12), (15, 18), (21, 24)]

def normalize_card(card: str) -> str:
    """Normalise les formats de cartes pour assurer le matching parfait"""
    if not card:
        return ""
    normalized = unicodedata.normalize('NFC', card)
    normalized = normalized.replace("♥️", "❤️")
    return normalized

class CardPredictor:
    """Gère la logique de prédiction d'ENSEIGNE (Couleur) et la vérification."""

    def __init__(self, telegram_message_sender=None):
        # <<<<<<<<<<<<<<<< ZONE CRITIQUE À MODIFIER PAR L'UTILISATEUR >>>>>>>>>>>>>>>>
        self.HARDCODED_SOURCE_ID = -1002682552255      # ID du canal SOURCE
        self.HARDCODED_PREDICTION_ID = -1003329818758   # ID du canal PRÉDICTION
        # <<<<<<<<<<<<<<<< FIN ZONE CRITIQUE >>>>>>>>>>>>>>>>
        
        self._last_rule_index = 0
        self._last_trigger_used = None
        self.telegram_message_sender = telegram_message_sender

        # --- A. Chargement des Données ---
        self.predictions = self._load_data('predictions.json', force_dict=True) 
        self.processed_messages = self._load_data('processed.json', is_set=True) 
        self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True) or 0
        self.last_predicted_game_number = self._load_data('last_predicted_game_number.json', is_scalar=True) or 0
        self.consecutive_fails = self._load_data('consecutive_fails.json', is_scalar=True) or 0
        self.pending_edits: Dict[int, Dict] = self._load_data('pending_edits.json', force_dict=True)
        
        # --- B. Configuration Canaux ---
        raw_config = self._load_data('channels_config.json', force_dict=True)
        self.config_data = raw_config if isinstance(raw_config, dict) else {}
        
        self.target_channel_id = self.config_data.get('target_channel_id') or self.HARDCODED_SOURCE_ID
        self.prediction_channel_id = self.config_data.get('prediction_channel_id') or self.HARDCODED_PREDICTION_ID
        
        # --- C. Logique INTER ---
        self.active_admin_chat_id = self._load_data('active_admin_chat_id.json', is_scalar=True)
        self.sequential_history: Dict[int, Dict] = self._load_data('sequential_history.json', force_dict=True) 
        self.inter_data: List[Dict] = self._load_data('inter_data.json') 
        self.is_inter_mode_active = self._load_data('inter_mode_status.json', is_scalar=True)
        self.smart_rules = self._load_data('smart_rules.json') 
        self.last_analysis_time = self._load_data('last_analysis_time.json', is_scalar=True) or 0
        self.collected_games = self._load_data('collected_games.json', is_set=True)
        
        self.quarantined_rules = self._load_data('quarantined_rules.json', force_dict=True)
        self.last_inter_update_time = self._load_data('last_inter_update.json', is_scalar=True) or 0
        self.last_report_sent = self._load_data('last_report_sent.json', force_dict=True)
        
        if self.is_inter_mode_active is None:
            self.is_inter_mode_active = True
        
        self.prediction_cooldown = 30
        self.last_suit_predictions = deque(maxlen=3)

        if self.inter_data and self.is_inter_mode_active and not self.smart_rules:
             self.analyze_and_set_smart_rules(initial_load=True)

    # --- Persistance ---
    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False, force_dict: bool = False) -> Any:
        try:
            expects_dict = force_dict or filename in ['channels_config.json', 'predictions.json', 'sequential_history.json', 'pending_edits.json', 'quarantined_rules.json', 'last_report_sent.json']
            
            if not os.path.exists(filename):
                if is_set: return set()
                if is_scalar: return None
                return {} if expects_dict else []
                
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    if is_set: return set()
                    if is_scalar: return None
                    return {} if expects_dict else []
                    
                data = json.loads(content)
                if is_set:
                    return set(data) if isinstance(data, list) else set()
                if expects_dict:
                    if isinstance(data, dict):
                        if filename in ['sequential_history.json', 'predictions.json', 'pending_edits.json']:
                            return {int(k): v for k, v in data.items()}
                        return data
                    return {}
                return data
        except Exception as e:
            logger.error(f"❌ Erreur chargement {filename}: {e}")
            if is_set: return set()
            if is_scalar: return None
            return {} if force_dict else []

    def _save_data(self, data: Any, filename: str):
        try:
            if isinstance(data, set):
                data = list(data)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde {filename}: {e}")

    def _save_all_data(self):
        self._save_data(self.predictions, 'predictions.json')
        self._save_data(self.processed_messages, 'processed.json')
        self._save_data(self.last_prediction_time, 'last_prediction_time.json')
        self._save_data(self.last_predicted_game_number, 'last_predicted_game_number.json')
        self._save_data(self.consecutive_fails, 'consecutive_fails.json')
        self._save_data(self.inter_data, 'inter_data.json')
        self._save_data(self.sequential_history, 'sequential_history.json')
        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')
        self._save_data(self.active_admin_chat_id, 'active_admin_chat_id.json')
        self._save_data(self.last_analysis_time, 'last_analysis_time.json')
        self._save_data(self.pending_edits, 'pending_edits.json')
        self._save_data(self.collected_games, 'collected_games.json')
        self._save_data(self.quarantined_rules, 'quarantined_rules.json')
        self._save_data(self.last_inter_update_time, 'last_inter_update.json')
        self._save_data(self.last_report_sent, 'last_report_sent.json')

    # ======== TEMPS & SESSIONS ========
    def now(self):
        return datetime.now(BENIN_TZ)
    
    def is_in_session(self):
        h = self.now().hour
        return any(start <= h < end for start, end in PREDICTION_SESSIONS)
    
    def current_session_label(self):
        h = self.now().hour
        for start, end in PREDICTION_SESSIONS:
            if start <= h < end:
                return f"{start:02d}h00 – {end:02d}h00"
        return "Hors session"
    
    # ======== RAPPORTS ========
    def check_and_send_scheduled_reports(self):
        """Envoie les rapports de fin de session (appelé régulièrement)."""
        if not self.telegram_message_sender or not self.prediction_channel_id:
            logger.debug("⚠️ Pas de sender ou prediction_channel_id")
            return
        
        now = self.now()
        key_date = now.strftime("%Y-%m-%d")
        
        # Heures de fin de session : 6h, 12h, 18h, 00h (minuit)
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        
        # Vérifier si c'est une heure de rapport (minute 0 pour être précis)
        if now.hour not in report_hours or now.minute != 0:
            return
        
        key = f"{key_date}_{now.hour}"
        
        # Éviter d'envoyer deux fois
        if self.last_report_sent.get(key):
            return
        
        logger.info(f"📊 Envoi rapport de session à {now.hour}h...")
        
        self.last_report_sent[key] = True
        report = self.generate_full_report(now)
        self.telegram_message_sender(self.prediction_channel_id, report)
        self._save_all_data()

    def generate_full_report(self, current_time: datetime) -> str:
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        hour = current_time.hour
        start, end = report_hours.get(hour, ("??", "??"))
        
        session_preds = {k: v for k, v in self.predictions.items() if v.get('status') in ['won', 'lost']}
        total = len(session_preds)
        wins = sum(1 for p in session_preds.values() if p.get('status') == 'won')
        fails = sum(1 for p in session_preds.values() if p.get('status') == 'lost')
        
        msg = (f"🎬 **BILAN DE SESSION**\n\n"
               f"⏰ Heure de Bénin : {current_time.strftime('%H:%M:%S - %d/%m/%Y')}\n"
               f"📅 Session : {start} – {end}\n"
               f"🧠 Mode : {'✅ INTER ACTIF' if self.is_inter_mode_active else '❌ STATIQUE'}\n\n"
               f"📈 Résultats: Total {total} | ✅ {wins} | ❌ {fails}\n\n"
               f"👨‍💻 Dev: Sossou Kouamé\n🎟️ Code: Koua229")
        return msg

    def extract_game_number(self, message: str) -> Optional[int]:
        match = re.search(r'#N(\d+)\.', message, re.IGNORECASE) or re.search(r'🔵(\d+)🔵', message)
        return int(match.group(1)) if match else None

    def get_all_cards_in_first_group(self, message: str) -> List[str]:
        match = re.search(r'\(([^)]*)\)', message)
        if not match: return []
        normalized = match.group(1).replace(" ", "").replace("♥", "❤️").replace("♠", "♠️").replace("♦", "♦️").replace("♣", "♣️")
        cards = re.findall(r'(\d+|[AKQJ])(❤️|♠️|♦️|♣️)', normalized, re.IGNORECASE)
        return [normalize_card(f"{v.upper()}{s}") for v, s in cards]

    def collect_inter_data(self, game_number: int, message: str):
        cards = self.get_all_cards_in_first_group(message)
        if not cards: return
        first_card = cards[0]
        self.sequential_history[game_number] = {'carte': first_card, 'date': self.now().isoformat()}
        self.collected_games.add(game_number)
        n_minus_2 = game_number - 2
        if n_minus_2 in self.sequential_history:
            self.inter_data.append({
                'numero_resultat': game_number,
                'declencheur': self.sequential_history[n_minus_2]['carte'],
                'result_suit': first_card[-2:],
                'date': self.now().isoformat()
            })
        limit = game_number - 50
        self.sequential_history = {k: v for k, v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        self._save_all_data()

    def analyze_and_set_smart_rules(self, chat_id=None, initial_load=False, force_activate=False):
        if len(self.inter_data) < 3: return
        groups = defaultdict(lambda: defaultdict(int))
        for e in self.inter_data:
            groups[e['result_suit']][normalize_card(e['declencheur'])] += 1
        new_rules = []
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            triggers = sorted(groups[suit].items(), key=lambda x: x[1], reverse=True)
            for rank, (t, count) in enumerate(triggers[:4], 1):
                new_rules.append({'trigger': t, 'predict': suit, 'count': count, 'rank': rank})
        self.smart_rules = new_rules
        self.last_inter_update_time = time.time()
        if force_activate: self.is_inter_mode_active = True
        self._save_all_data()

    def _get_active_rules(self) -> List[Dict]:
        active = []
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            # S'assurer que smart_rules est une liste de dicts
            suit_rules = [r for r in self.smart_rules if isinstance(r, dict) and r.get('predict') == suit]
            
            # S'assurer que quarantined_rules[suit] est un dictionnaire
            if suit not in self.quarantined_rules or not isinstance(self.quarantined_rules[suit], dict):
                self.quarantined_rules[suit] = {}
            
            q = self.quarantined_rules[suit]
            available = [r for r in suit_rules if r.get('trigger') not in q]
            
            if len(available) < 4 and q:
                # Libérer les règles les moins utilisées si besoin
                sorted_q = sorted(q.items(), key=lambda x: x[1])
                for t_name, count in sorted_q[:4-len(available)]:
                    if t_name in self.quarantined_rules[suit]:
                        del self.quarantined_rules[suit][t_name]
                # Recalculer available après libération
                available = [r for r in suit_rules if r.get('trigger') not in self.quarantined_rules[suit]]
            
            active.extend(available[:4])
        return active

    def make_prediction(self, game_number: int, message: str) -> Optional[Dict]:
        if not self.is_in_session(): 
            logger.debug("⏳ Hors session de prédiction")
            return None
        # if game_number <= self.last_predicted_game_number + 2: 
        #     logger.debug(f"⏳ Écart de 3 non respecté ({game_number} <= {self.last_predicted_game_number}+2)")
        #     return None
        
        cards = self.get_all_cards_in_first_group(message)
        if not cards: return None
        trigger_card = cards[0]
        
        prediction = None
        # 1. Règles Statiques
        if trigger_card in STATIC_RULES:
            prediction = {'suit': STATIC_RULES[trigger_card], 'type': 'STATIC'}
            logger.info(f"🎯 Match Règle STATIQUE: {trigger_card} -> {prediction['suit']}")
        
        # 2. Règles INTER
        if not prediction and self.is_inter_mode_active:
            active = self._get_active_rules()
            # Normalisation du déclencheur dans la règle
            match = next((r for r in active if normalize_card(r['trigger']) == trigger_card), None)
            if match:
                # Anti-répétition 2x
                if list(self.last_suit_predictions).count(match['predict']) >= 2:
                    logger.debug(f"🚫 Anti-répétition: {match['predict']} déjà prédit 2x")
                    return None
                prediction = {'suit': match['predict'], 'type': 'INTER', 'rule': match}
                logger.info(f"🎯 Match Règle INTER: {trigger_card} → {prediction['suit']}")

        if prediction:
            target_game = game_number + 2
            self.last_predicted_game_number = game_number
            self.last_suit_predictions.append(prediction['suit'])
            pred_data = {
                'target_game': target_game,
                'predicted_suit': prediction['suit'],
                'trigger_card': trigger_card,
                'status': 'pending',
                'type': prediction['type'],
                'timestamp': time.time()
            }
            self.predictions[target_game] = pred_data
            if prediction['type'] == 'INTER':
                rule = prediction['rule']
                s = rule.get('predict')
                if s and s not in self.quarantined_rules: self.quarantined_rules[s] = {}
                rule_trigger = rule.get('trigger')
                if s and rule_trigger:
                    self.quarantined_rules[s][rule_trigger] = self.quarantined_rules[s].get(rule_trigger, 0) + 1
            self._save_all_data()
            return pred_data
        
        logger.debug(f"❌ Aucune règle ne correspond à {trigger_card}")
        return None

    def verify_prediction(self, game_number: int, message: str) -> Optional[Dict]:
        if game_number not in self.predictions: return None
        pred = self.predictions[game_number]
        if pred['status'] != 'pending': return None
        
        cards = self.get_all_cards_in_first_group(message)
        if not cards: return None
        
        # Vérification sur les 3 premières cartes (Martingale G0, G1, G2)
        # On cherche l'offset (0 = G0, 1 = G1, 2 = G2)
        win_offset = None
        for i, card in enumerate(cards[:3]):
            if card[-2:] == pred['predicted_suit']:
                win_offset = i
                break
        
        if win_offset is not None:
            pred['status'] = 'won'
            pred['win_offset'] = win_offset
            pred['status_symbol'] = SYMBOL_MAP.get(win_offset, '✅')
        else:
            pred['status'] = 'lost'
            pred['status_symbol'] = SYMBOL_MAP.get('lost', '❌')
            
        pred['result_cards'] = cards[:3]
        self._save_all_data()
        return pred
