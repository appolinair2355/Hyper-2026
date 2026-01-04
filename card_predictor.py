# card_predictor.py - VERSION DEBUG ULTIME
import re
import logging
import time
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict, deque, Counter
import pytz
import unicodedata

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # MODE DEBUG MAXIMUM

# ================== CONFIGURATION ==================
BENIN_TZ = pytz.timezone("Africa/Porto-Novo")
PREDICTION_CHANNEL_ID = -1003554569009

# Règles statiques
STATIC_RULES = {
    "10♦️": "♠️", "10♠️": "❤️", "9♣️": "❤️", "9♦️": "♠️",
    "8♣️": "♠️", "8♠️": "♣️", "7♠️": "♠️", "7♣️": "♣️",
    "6♦️": "♣️", "6♣️": "♦️", "A❤️": "❤️", "5❤️": "❤️", "5♠️": "♠️"
}

# Sessions de prédictions
PREDICTION_SESSIONS = [(1, 6), (9, 12), (15, 18), (21, 24)]

# Trackers globaux
last_suit_predictions = deque(maxlen=3)
last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}

# ================== NORMALISATION ==================
def normalize_card(card: str) -> str:
    """Normalise les formats de cartes pour assurer le matching parfait"""
    if not card:
        return ""
    normalized = unicodedata.normalize('NFC', card)
    normalized = normalized.replace("♥️", "❤️")
    return normalized

class CardPredictor:
    def __init__(self, telegram_message_sender=None):
        # <<<<<<<<< ZONE À MODIFIER >>>>>>>>>
        self.HARDCODED_SOURCE_ID = -1002682552255
        self.HARDCODED_PREDICTION_ID = -1003554569009
        # <<<<<<<<< FIN ZONE >>>>>>>>>
        
        self.telegram_message_sender = telegram_message_sender
        self._last_rule_index = 0
        self._last_trigger_used = None
        
        # --- Chargement des données avec PROTECTION ---
        logger.info("📂 CHARGEMENT DES DONNÉES...")
        self.predictions = self._load_data('predictions.json', force_dict=True, default_if_corrupt={})
        self.inter_data = self._load_data('inter_data.json', default_if_corrupt=[])
        self.collected_games = self._load_data('collected_games.json', is_set=True, default_if_corrupt=set())
        self.sequential_history = self._load_data('sequential_history.json', force_dict=True, default_if_corrupt={})
        self.smart_rules = self._load_data('smart_rules.json', default_if_corrupt=[])
        self.all_time_rules = self._load_data('all_time_rules.json', default_if_corrupt=[])
        self.quarantined_rules = self._load_data('quarantined_rules.json', force_dict=True, default_if_corrupt={})
        
        # Trackers temporels
        self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True, default_if_corrupt=0)
        self.last_predicted_game_number = self._load_data('last_predicted_game_number.json', is_scalar=True, default_if_corrupt=0)
        self.last_analysis_time = self._load_data('last_analysis_time.json', is_scalar=True, default_if_corrupt=0)
        self.wait_until_next_update = 0
        
        # Configuration des canaux
        self.config_data = self._load_data('channels_config.json', force_dict=True, default_if_corrupt={})
        self.target_channel_id = self.config_data.get('target_channel_id') or self.HARDCODED_SOURCE_ID
        self.prediction_channel_id = self.config_data.get('prediction_channel_id') or self.HARDCODED_PREDICTION_ID
        
        # Mode INTER et bilans
        self.is_inter_mode_active = self._load_data('inter_mode_status.json', is_scalar=True, default_if_corrupt=False)
        self.bilan_times = [6, 12, 18, 0]
        self.last_report_sent = self._load_data('last_report_sent.json', force_dict=True, default_if_corrupt={})
        self.last_inter_update_time = self._load_data('last_inter_update.json', is_scalar=True, default_if_corrupt=0)
        
        # Cooldown
        self.prediction_cooldown = 30
        
        logger.info(f"✅ CardPredictor initialisé:")
        logger.info(f"   - {len(self.inter_data)} jeux collectés")
        logger.info(f"   - {len(self.smart_rules)} règles créées")
        logger.info(f"   - Mode INTER: {'ACTIF' if self.is_inter_mode_active else 'INACTIF'}")
        logger.info(f"   - Canal Source: {self.target_channel_id}")
        logger.info(f"   - Canal Pred: {self.prediction_channel_id}")

    # --- PERSISTENCE avec PROTECTION ANTI-CORRUPTION ---
    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False, 
                   force_dict: bool = False, default_if_corrupt: Any = None) -> Any:
        """
        Chargement SÉCURISÉ avec protection contre les erreurs de type
        """
        try:
            expects_dict = force_dict or filename in [
                'channels_config.json', 'predictions.json', 'sequential_history.json', 
                'quarantined_rules.json', 'last_report_sent.json'
            ]
            
            if not os.path.exists(filename):
                if default_if_corrupt is not None:
                    return default_if_corrupt
                return set() if is_set else (None if is_scalar else ({} if expects_dict else []))
            
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    if default_if_corrupt is not None:
                        return default_if_corrupt
                    return set() if is_set else (None if is_scalar else ({} if expects_dict else []))
                
                data = json.loads(content)
                
                # ✅ PROTECTION CRITIQUE: Vérification du type
                if expects_dict and not isinstance(data, dict):
                    logger.error(f"❌ CORRUPTION DÉTECTÉE: {filename} devrait être un dict, mais c'est un {type(data).__name__}")
                    logger.error(f"   Contenu: {str(data)[:100]}...")
                    if default_if_corrupt is not None:
                        return default_if_corrupt
                    return {}
                
                if is_set and not isinstance(data, list):
                    logger.warning(f"⚠️ {filename} devrait être une liste pour is_set, conversion forcée")
                    return set() if default_if_corrupt is None else default_if_corrupt
                
                # Conversion des types
                if is_set:
                    return set(data) if isinstance(data, list) else (set() if default_if_corrupt is None else default_if_corrupt)
                
                # Conversion des clés en int pour certains fichiers
                if isinstance(data, dict) and filename in ['sequential_history.json', 'predictions.json']:
                    try:
                        return {int(k): v for k, v in data.items()}
                    except (ValueError, TypeError) as e:
                        logger.error(f"❌ Erreur conversion clés en int pour {filename}: {e}")
                        return {} if default_if_corrupt is None else default_if_corrupt
                
                return data
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ CORRUPTION JSON dans {filename}: {e}")
            if default_if_corrupt is not None:
                return default_if_corrupt
            return set() if is_set else (None if is_scalar else ({} if expects_dict else []))
        
        except Exception as e:
            logger.error(f"❌ Erreur inattendue chargement {filename}: {e}")
            if default_if_corrupt is not None:
                return default_if_corrupt
            return set() if is_set else (None if is_scalar else ({} if expects_dict else []))

    def _save_data(self, data: Any, filename: str):
        """Sauvegarde SÉCURISÉE des données avec gestion des types"""
        try:
            if isinstance(data, set):
                data = list(data)
            
            # S'assurer que channels_config.json a des IDs int
            if filename == 'channels_config.json' and isinstance(data, dict):
                for key in ['target_channel_id', 'prediction_channel_id']:
                    if key in data and data[key] is not None:
                        try:
                            data[key] = int(data[key])
                        except (ValueError, TypeError):
                            logger.error(f"❌ Impossible de convertir {key} en int: {data[key]}")
                            data[key] = 0
            
            # Sauvegarde avec validation JSON
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
        except Exception as e:
            logger.error(f"❌ ERREUR CRITIQUE sauvegarde {filename}: {e}")

    def _save_all_data(self):
        """Sauvegarde TOUS les fichiers de données avec validation"""
        try:
            logger.info("💾 SAUVEGARDE DE TOUS LES FICHIERS...")
            self._save_data(self.predictions, 'predictions.json')
            self._save_data(self.inter_data, 'inter_data.json')
            self._save_data(self.collected_games, 'collected_games.json')
            self._save_data(self.sequential_history, 'sequential_history.json')
            self._save_data(self.smart_rules, 'smart_rules.json')
            self._save_data(self.all_time_rules, 'all_time_rules.json')
            self._save_data(self.quarantined_rules, 'quarantined_rules.json')
            self._save_data(self.last_prediction_time, 'last_prediction_time.json')
            self._save_data(self.last_predicted_game_number, 'last_predicted_game_number.json')
            self._save_data(self.last_analysis_time, 'last_analysis_time.json')
            self._save_data(self._last_trigger_used, 'last_trigger_used.json')
            self._save_data(self._last_rule_index, 'last_rule_index.json')
            self._save_data(self.config_data, 'channels_config.json')
            self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
            self._save_data(self.last_report_sent, 'last_report_sent.json')
            self._save_data(self.last_inter_update_time, 'last_inter_update.json')
            self._save_data(self.wait_until_next_update, 'wait_until_next_update.json')
            logger.info("✅ Toutes les données sauvegardées avec succès")
        except Exception as e:
            logger.error(f"❌ ERREUR CRITIQUE sauvegarde globale: {e}")

    # --- TEMPS & SESSIONS ---
    def now(self):
        return datetime.now(BENIN_TZ)

    def is_in_session(self):
        h = self.now().hour
        in_sess = any(start <= h < end for start, end in PREDICTION_SESSIONS)
        logger.debug(f"⏰ Vérification session: {h}h -> {'✅ DANS SESSION' if in_sess else '❌ HORS SESSION'}")
        return in_sess

    def current_session_label(self):
        h = self.now().hour
        for start, end in PREDICTION_SESSIONS:
            if start <= h < end:
                return f"{start:02d}h00 – {end:02d}h00"
        return "Hors session"

    # --- BILANS HORAIRES (EXACTES) ---
    def check_and_send_scheduled_reports(self):
        """Envoie les bilans AUX HEURES EXACTES (6h, 12h, 18h, 00h)"""
        if not self.telegram_message_sender or not self.prediction_channel_id:
            logger.warning("🚫 Pas de sender ou canal de prédiction configuré")
            return
        
        now = self.now()
        
        # ✅ Vérification EXACTE de l'heure (minute = 0)
        if now.minute == 0 and now.hour in self.bilan_times:
            key = f"{now.day}_{now.hour}"
            
            if self.last_report_sent.get(key):
                logger.debug(f"📊 Bilan {key} déjà envoyé")
                return
            
            self.last_report_sent[key] = True
            
            report = self.generate_full_report(now)
            self.telegram_message_sender(self.prediction_channel_id, report)
            logger.info(f"📊 BILAN ENVOYÉ: {now.hour:02d}h00 pile")
            self._save_all_data()
        else:
            logger.debug(f"⏰ Pas heure de bilan: {now.hour:02d}h{now.minute:02d}")

    def generate_full_report(self, current_time: datetime) -> str:
        """Génère le bilan complet de la session"""
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 
                       18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        start, end = report_hours.get(current_time.hour, ("??", "??"))
        
        session_predictions = {k: v for k, v in self.predictions.items() 
                              if v.get('status') in ['won', 'lost', 'pending']}
        total = len(session_predictions)
        wins = sum(1 for p in session_predictions.values() if p.get('status') == 'won')
        fails = sum(1 for p in session_predictions.values() if p.get('status') == 'lost')
        total_quarantined = sum(len(q) for q in self.quarantined_rules.values())
        
        return (
            f"📊 **BILAN HORAIRE - {current_time.strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
            f"🎯 Session: {start} – {end}\n"
            f"🧠 Mode: {'✅ INTER ACTIF' if self.is_inter_mode_active else '❌ STATIQUE'}\n"
            f"🔄 Règles actives: {len(self.smart_rules)}/16 | Quarantaine: {total_quarantined}\n\n"
            f"📈 **RÉSULTATS**\n"
            f"Total: {total} | ✅ {wins} | ❌ {fails}\n\n"
            f"👨‍💻 Dev: Sossou Kouamé\n"
            f"🎟️ Code: Koua229"
        )

    def get_session_report_preview(self) -> str:
        """Aperçu du prochain bilan"""
        now = self.now()
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 
                       18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        
        next_report_hour = None
        for h in sorted(report_hours.keys()):
            if h > now.hour:
                next_report_hour = h
                break
        if next_report_hour is None:
            next_report_hour = min(report_hours.keys())
        
        minutes_until = ((next_report_hour - now.hour) * 60 - now.minute) % (24 * 60)
        hours = minutes_until // 60
        mins = minutes_until % 60
        start, end = report_hours[next_report_hour]
        
        session_predictions = {k: v for k, v in self.predictions.items() 
                              if v.get('status') in ['won', 'lost', 'pending']}
        total = len(session_predictions)
        wins = sum(1 for p in session_predictions.values() if p.get('status') == 'won')
        
        return (
            f"📋 **APERÇU DU BILAN**\n\n"
            f"⏰ Heure: {now.strftime('%H:%M:%S - %d/%m/%Y')}\n"
            f"🎯 Prochain bilan: {start} – {end}\n"
            f"⏳ Temps restant: {hours}h{mins:02d}\n\n"
            f"🧠 Mode: {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}\n"
            f"📊 Stats: {total} prédictions | ✅ {wins} réussites"
        )

    def get_inter_version(self):
        if not self.last_inter_update_time:
            return "Base neuve"
        return datetime.fromtimestamp(self.last_inter_update_time, BENIN_TZ).strftime("%Y-%m-%d | %Hh%M")

    def _get_last_update_display(self):
        if not self.last_inter_update_time:
            return "Pas encore de mise à jour"
        return datetime.fromtimestamp(self.last_inter_update_time, BENIN_TZ).strftime("%d/%m/%Y à %H:%M:%S")

    def set_channel_id(self, channel_id: int, channel_type: str):
        if not isinstance(self.config_data, dict):
            self.config_data = {}
        if channel_type == 'source':
            self.target_channel_id = channel_id
            self.config_data['target_channel_id'] = channel_id
        elif channel_type == 'prediction':
            self.prediction_channel_id = channel_id
            self.config_data['prediction_channel_id'] = channel_id
        self._save_data(self.config_data, 'channels_config.json')
        return True

    # --- EXTRACTION ROBUSTE ---
    def _extract_parentheses_content(self, text: str) -> List[str]:
        pattern = r'\(([^)]+)\)'
        return re.findall(pattern, text)

    def extract_game_number(self, message: str) -> Optional[int]:
        match = re.search(r'#N(\d+)\.', message, re.IGNORECASE)
        if not match:
            match = re.search(r'🔵(\d+)🔵', message)
        return int(match.group(1)) if match else None

    def extract_game_number_from_text(self, text: str) -> Optional[int]:
        patterns = [
            r'#N(\d+)\.', r'🔵(\d+)🔵', r'Jeu\s*(\d+)', r'J\s*(\d+)', r'GAME\s*(\d+)',
            r'N°\s*(\d+)', r'#(\d+)', r'\b(\d{1,4})\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                if 1 <= num <= 9999:
                    return num
        return None

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        normalized = content.replace(" ", "")
        normalized = normalized.replace("♥", "❤️").replace("♥️", "❤️")
        normalized = normalized.replace("♠", "♠️").replace("♠️", "♠️")
        normalized = normalized.replace("♦", "♦️").replace("♦️", "♦️")
        normalized = normalized.replace("♣", "♣️").replace("♣️", "♣️")
        pattern = r'(\d+|[AKQJ])(❤️|♠️|♦️|♣️)'
        matches = re.findall(pattern, normalized, re.IGNORECASE)
        formatted = [(value.upper(), suit) for value, suit in matches]
        logger.debug(f"🃏 Cartes extraites: {formatted}")
        return formatted

    def get_all_cards_in_first_group(self, message: str) -> List[str]:
        """Retourne TOUTES les cartes du PREMIER groupe (NORMALISÉES)"""
        match = re.search(r'\(([^)]*)\)', message)
        if not match:
            logger.debug("❌ Aucun groupe de parenthèses trouvé")
            return []
        
        details = self.extract_card_details(match.group(1))
        cards = []
        for v, c in details:
            card = f"{v.upper()}{c}"
            normalized_card = normalize_card(card)  # ✅ NORMALISATION CRITIQUE
            cards.append(normalized_card)
        
        logger.info(f"📌 PREMIER GROUPE NORMALISÉ: {cards}")
        return cards

    def get_first_card_info(self, message: str) -> Optional[Tuple[str, str]]:
        all_cards = self.get_all_cards_in_first_group(message)
        if all_cards:
            return all_cards[0], all_cards[0][-2:]
        return None

    # --- COLLECTE DES DONNÉES ---
    def collect_inter_data(self, game_number: int, message: str):
        """Collecte les données (N-2 -> N)"""
        logger.info(f"📊 TENTATIVE COLLECTE JEU {game_number}")
        
        info = self.get_first_card_info(message)
        if not info:
            logger.warning(f"❌ Aucune carte trouvée pour collecte J{game_number}")
            return
        
        full_card, suit = info
        trigger_card_normalized = normalize_card(full_card)
        result_suit_normalized = suit.replace("❤️", "♥️")
        
        logger.info(f"📌 Carte extraite: {trigger_card_normalized} → Résultat: {result_suit_normalized}")
        
        if game_number in self.collected_games:
            existing = self.sequential_history.get(game_number)
            if existing and existing.get('carte') == trigger_card_normalized:
                logger.debug(f"🧠 Jeu {game_number} déjà collecté, ignoré.")
                return
        
        self.sequential_history[game_number] = {'carte': trigger_card_normalized, 'date': datetime.now().isoformat()}
        self.collected_games.add(game_number)
        
        n_minus_2 = game_number - 2
        trigger_entry = self.sequential_history.get(n_minus_2)
        
        if trigger_entry:
            trigger_card = trigger_entry['carte']
            self.inter_data.append({
                'numero_resultat': game_number,
                'declencheur': trigger_card,
                'numero_declencheur': n_minus_2,
                'result_suit': result_suit_normalized,
                'date': datetime.now().isoformat()
            })
            logger.info(f"✅ DONNÉE COLLECTÉE: J{n_minus_2} ({trigger_card}) → J{game_number} ({result_suit_normalized})")
        else:
            logger.debug(f"⏳ Pas de déclencheur J{n_minus_2} pour J{game_number}")
        
        # Nettoyage
        limit = game_number - 50
        self.sequential_history = {k: v for k, v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        
        self._save_all_data()
        logger.info(f"💾 Données collectées sauvegardées. Total: {len(self.inter_data)} jeux")

    # --- ANALYSE ET CRÉATION DES 16 RÈGLES (TOP 4) ---
    def analyze_and_set_smart_rules(self, chat_id: Optional[int] = None, initial_load: bool = False, force_activate: bool = False):
        """Analyse les données et crée EXACTEMENT 16 règles (4 par costume)"""
        logger.info(f"🔍 DÉBUT ANALYSE - {len(self.inter_data)} jeux disponibles")
        
        if len(self.inter_data) < 3:
            logger.warning(f"⚠️ Pas assez de données: {len(self.inter_data)} jeux (minimum 3)")
            return
        
        result_suit_groups = defaultdict(lambda: defaultdict(int))
        
        for entry in self.inter_data:
            trigger_card = entry['declencheur']
            result_suit = entry['result_suit']
            result_normalized = result_suit.replace("♥️", "❤️")
            trigger_normalized = normalize_card(trigger_card)
            result_suit_groups[result_normalized][trigger_normalized] += 1
        
        self.smart_rules = []
        
        # Pour chaque costume, prendre les 4 meilleurs triggers
        for result_suit in ['♠️', '❤️', '♦️', '♣️']:
            triggers = result_suit_groups.get(result_suit, {})
            sorted_triggers = sorted(triggers.items(), key=lambda x: x[1], reverse=True)
            
            # ✅ TOP 4 EXACTEMENT
            for rank, (trigger, count) in enumerate(sorted_triggers[:4], 1):
                self.smart_rules.append({
                    'trigger': trigger,
                    'predict': result_suit,
                    'count': count,
                    'rank': rank
                })
        
        # Libérer les règles de la quarantaine si nécessaire
        self.smart_rules = self._get_active_rules()
        
        if force_activate:
            self.is_inter_mode_active = True
        
        self.last_inter_update_time = time.time()
        self._save_all_data()
        
        logger.info(f"✅ ANALYSE TERMINÉE: {len(self.smart_rules)} règles créées")
        logger.info(f"📋 Règles: {[f'{r['trigger']}→{r['predict']}({r['count']}x)' for r in self.smart_rules]}")
        
        if chat_id and self.telegram_message_sender:
            msg, _ = self.get_inter_status()
            self.telegram_message_sender(chat_id, msg)

    def _get_active_rules(self) -> List[Dict]:
        """Sélectionne les 16 règles actives (4 par costume, hors quarantaine temporaire)"""
        active_rules = []
        
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            # S'assurer que smart_rules est une liste de dicts
            if not isinstance(self.smart_rules, list):
                logger.error(f"❌ CORRUPTION: smart_rules n'est pas une liste")
                return []
            
            suit_rules = [r for r in self.smart_rules if isinstance(r, dict) and r.get('predict') == suit]
            
            # S'assurer que quarantined_rules[suit] est un dictionnaire
            if suit not in self.quarantined_rules or not isinstance(self.quarantined_rules[suit], dict):
                self.quarantined_rules[suit] = {}
            
            quarantined = self.quarantined_rules[suit]
            available = [r for r in suit_rules if r['trigger'] not in quarantined]
            
            # Si moins de 4 disponibles, libérer les règles les moins utilisées
            if len(available) < 4 and quarantined:
                sorted_quarantined = sorted(quarantined.items(), key=lambda x: x[1])
                triggers_to_restore = [t for t, count in sorted_quarantined[:4 - len(available)]]
                
                for trigger in triggers_to_restore:
                    if trigger in self.quarantined_rules[suit]:
                        del self.quarantined_rules[suit][trigger]
                
                available = [r for r in suit_rules if r['trigger'] not in self.quarantined_rules[suit]]
            
            active_rules.extend(available[:4])
        
        return active_rules

    def check_and_update_rules(self):
        """Mise à jour périodique (10 minutes) - CORRIGÉ"""
        if time.time() - self.last_analysis_time > 600:  # 600 = 10 minutes
            logger.info("🔄 Mise à jour INTER périodique (10 min)")
            if len(self.inter_data) >= 3:
                self.analyze_and_set_smart_rules(force_activate=True)
            else:
                logger.warning(f"⚠️ Pas assez de données: {len(self.inter_data)} jeux")

    # --- PRÉDICTION CRITIQUE (CORRIGÉE) ---
    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str], Optional[bool]]:
        """
        DÉTERMINE SI ON DOIT PRÉDIRE - LOGIQUE CORRIGÉE AVEC ÉCART DE 3
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 ANALYSE MESSAGE: {message[:100]}")
        logger.info(f"{'='*60}")
        
        # Vérification session
        if not self.is_in_session():
            logger.warning(f"⚠️ Hors session. Heure Benin: {self.now().hour}h")
            return False, None, None, None
        
        # Vérification prédiction en attente
        pending = [p for p in self.predictions.values() if p.get('status') == 'pending']
        if pending:
            logger.warning(f"⚠️ Prédiction déjà en attente: {len(pending)}")
            return False, None, None, None
        
        # Vérification cooldown
        if time.time() < self.wait_until_next_update:
            logger.debug("⏸️ Cooldown après échec/quarantaine actif")
            return False, None, None, None
        
        # Extraction numéro de jeu
        game_number = self.extract_game_number_from_text(message)
        if not game_number:
            logger.error("❌ Numéro de jeu non trouvé")
            return False, None, None, None
        
        logger.info(f"🎮 NUMÉRO DE JEU: {game_number}")
        
        # ✅ ÉCART STRICT DE 3: Vérification que le numéro est >= dernier + 3
        if self.last_predicted_game_number and (game_number < self.last_predicted_game_number + 3):
            logger.error(f"⏳ ÉCART DE 3 NON RESPECTÉ: {game_number} < {self.last_predicted_game_number + 3}")
            logger.error(f"   Dernier prédict: J{self.last_predicted_game_number}, Attendu: J{self.last_predicted_game_number + 3}")
            return False, None, None, None
        
        # Extraction cartes du premier groupe
        all_cards = self.get_all_cards_in_first_group(message)
        if not all_cards:
            logger.error("❌ Aucune carte trouvée dans le premier groupe")
            return False, None, None, None
        
        logger.info(f"🃏 CARTES TROUVÉES: {all_cards}")
        
        predicted_suit = None
        trigger_used = None
        is_inter_prediction = False
        rule_index = 0
        
        # ======= MODE INTER : TOP 4 (PRIORITÉ ABSOLUE) =======
        if self.is_inter_mode_active and self.smart_rules:
            logger.info(f"🧠 MODE INTER ACTIF - {len(self.smart_rules)} règles disponibles")
            
            rules_by_suit = defaultdict(list)
            for rule in self.smart_rules:
                if isinstance(rule, dict) and 'predict' in rule:
                    rules_by_suit[rule['predict']].append(rule)
            
            # Chercher dans les 4 TOP de chaque couleur
            for suit in ['♠️', '❤️', '♦️', '♣️']:
                suit_rules = sorted(rules_by_suit.get(suit, []), key=lambda x: x.get('count', 0), reverse=True)
                top4 = suit_rules[:4]  # ✅ TOP 4 EXACTEMENT
                
                logger.debug(f"🔍 Vérification costume {suit}: {len(top4)} règles disponibles")
                
                for idx, rule in enumerate(top4):
                    if not isinstance(rule, dict) or 'trigger' not in rule:
                        logger.warning(f"⚠️ Règle invalide: {rule}")
                        continue
                    
                    normalized_trigger = normalize_card(rule['trigger'])
                    logger.debug(f"   TEST: '{normalized_trigger}' dans {all_cards}?")
                    
                    if normalized_trigger in all_cards:
                        key = f"{rule['trigger']}_{rule['predict']}"
                        
                        # Vérifier quarantaine
                        if key in self.quarantined_rules:
                            qua_data = self.quarantined_rules[key]
                            if isinstance(qua_data, dict) and time.time() < qua_data.get('expires_at', 0):
                                logger.debug(f"   🔒 Règle en quarantaine: {key}")
                                continue
                        
                        predicted_suit = rule['predict']
                        trigger_used = rule['trigger']
                        is_inter_prediction = True
                        rule_index = idx + 1
                        logger.info(f"✅✅✅ MATCH TROUVÉ: {normalized_trigger} → {predicted_suit} (TOP{rule_index}) ✅✅✅")
                        break
                
                if predicted_suit:
                    break
            
            if not predicted_suit:
                logger.error("❌ AUCUNE RÈGLE TOP4 NE MATCH")
                logger.error(f"Cartes: {all_cards}")
                logger.error(f"Règles disponibles: {[normalize_card(r['trigger']) for r in self.smart_rules if isinstance(r, dict)]}")
        
        # ======= MODE STATIQUE (UNIQUEMENT SI INTER INACTIF) =======
        elif not self.is_inter_mode_active:
            logger.info("📋 MODE STATIQUE ACTIF")
            for card in all_cards:
                if card in STATIC_RULES:
                    predicted_suit = STATIC_RULES[card]
                    trigger_used = card
                    is_inter_prediction = False
                    rule_index = 0
                    logger.info(f"✅ MATCH RÈGLE STATIQUE: {card} → {predicted_suit}")
                    break
        
        # ✅ PRÉDICTION TROUVÉE
        if predicted_suit:
            # Anti-répétition (max 2 fois le même costume)
            if list(self.last_suit_predictions).count(predicted_suit) >= 2:
                logger.warning(f"🚫 ANTI-RÉPÉTITION: Costume {predicted_suit} déjà prédict 2x d'affilée")
                return False, None, None, None
            
            if self.last_prediction_time and time.time() < self.last_prediction_time + self.prediction_cooldown:
                logger.debug("⏸️ Cooldown prédiction actif")
                return False, None, None, None
            
            self._last_rule_index = rule_index
            self._last_trigger_used = trigger_used
            logger.info(f"🚀 PRÉDICTION VALIDÉE: J{game_number} → {predicted_suit} (trigger: {trigger_used})")
            return True, game_number, predicted_suit, is_inter_prediction
        
        logger.warning("❌ AUCUNE PRÉDICTION POSSIBLE")
        return False, None, None, None

    def prepare_prediction_text(self, game_number_source: int, predicted_costume: str) -> str:
        target_game = game_number_source + 2
        text = f"🔵{target_game}🔵:{predicted_costume} statut :⏳"
        logger.info(f"📝 PRÉDICTION PRÊTE: J{game_number_source} → J{target_game}, Costume: {predicted_costume}")
        return text

    def make_prediction(self, game_number_source: int, suit: str, message_id_bot: int, is_inter: bool = False, trigger_used: Optional[str] = None):
        """Enregistre la prédiction"""
        target = game_number_source + 2
        
        if not trigger_used:
            trigger_used = self._last_trigger_used or '?'
        
        rule_index = self._last_rule_index if is_inter else 0
        
        self.predictions[target] = {
            'predicted_costume': suit,
            'status': 'pending',
            'predicted_from': game_number_source,
            'predicted_from_trigger': trigger_used,
            'message_text': self.prepare_prediction_text(game_number_source, suit),
            'message_id': message_id_bot,
            'is_inter': is_inter,
            'rule_index': rule_index,
            'timestamp': time.time()
        }
        
        self.last_prediction_time = time.time()
        self.last_predicted_game_number = game_number_source
        
        if is_inter:
            self._mark_rule_as_used(trigger_used, suit)
        
        self._save_all_data()
        logger.info(f"🎯 PRÉDICTION ENREGISTRÉE: J{target} → {suit} (trigger: {trigger_used})")

    # --- VÉRIFICATION ---
    def verify_prediction(self, message: str) -> Optional[Dict]:
        return self._verify_prediction_common(message, is_edited=False)

    def verify_prediction_from_edit(self, message: str) -> Optional[Dict]:
        return self._verify_prediction_common(message, is_edited=True)

    def check_costume_in_first_parentheses(self, message: str, predicted_costume: str) -> bool:
        all_cards = self.get_all_cards_in_first_group(message)
        if not all_cards:
            return False
        
        normalized_predicted = normalize_card(predicted_costume)
        logger.debug(f"🔍 Vérification costume {normalized_predicted} dans {all_cards}")
        
        for card in all_cards:
            if normalized_predicted in card:
                logger.info(f"✅ Costume {normalized_predicted} trouvé dans {card}")
                return True
        
        return False

    def _verify_prediction_common(self, message: str, is_edited: bool = False) -> Optional[Dict]:
        """Logique de vérification commune"""
        self.check_and_send_reports()
        
        game_number = self.extract_game_number_from_text(message)
        if not game_number:
            return None
        
        logger.info(f"🔍 Vérification du jeu {game_number}...")
        
        if not self.is_final_result_structurally_valid(message):
            logger.debug(f"⚠️ Structure invalide pour jeu {game_number}")
            return None
        
        if not self.predictions:
            return None
        
        for predicted_game, prediction in self.predictions.items():
            if prediction.get('status') != 'pending':
                continue
            
            predicted_costume = prediction.get('predicted_costume')
            if not predicted_costume:
                continue
            
            offset = game_number - predicted_game
            
            if 0 <= offset <= 2:
                costume_found = self.check_costume_in_first_parentheses(message, predicted_costume)
                
                if costume_found:
                    status_symbol = f"✅{offset}️⃣"
                    logger.info(f"✅ SUCCÈS: J{predicted_game}+{offset} → {predicted_costume}")
                    prediction['status'] = 'won'
                    prediction['verification_offset'] = offset
                    updated_message = f"🔵{predicted_game}🔵:{predicted_costume} statut :{status_symbol}"
                    prediction['final_message'] = updated_message
                    
                    self._save_all_data()
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': str(predicted_game),
                        'new_message': updated_message,
                        'message_id_to_edit': prediction.get('message_id')
                    }
                
                elif offset == 2:
                    status_symbol = "❌"
                    logger.info(f"❌ ÉCHEC: Costume {predicted_costume} non trouvé au jeu {predicted_game}+2")
                    prediction['status'] = 'lost'
                    prediction['verification_offset'] = 2
                    updated_message = f"🔵{predicted_game}🔵:{predicted_costume} statut :{status_symbol}"
                    prediction['final_message'] = updated_message
                    
                    if prediction.get('is_inter'):
                        self._apply_quarantine(prediction)
                    
                    self._save_all_data()
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': str(predicted_game),
                        'new_message': updated_message,
                        'message_id_to_edit': prediction.get('message_id')
                    }
        
        return None

    def is_final_result_structurally_valid(self, text: str) -> bool:
        """Vérifie si la structure du message est valide"""
        matches = self._extract_parentheses_content(text)
        num_sections = len(matches)
        
        if num_sections < 2:
            return False
        
        if ('#T' in text or '🔵#R' in text) and num_sections >= 2:
            return True
        
        if num_sections == 2:
            def count_cards(content):
                normalized = content.replace("❤️", "♥️")
                return len(re.findall(r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)', normalized, re.IGNORECASE))
            
            count_1 = count_cards(matches[0])
            count_2 = count_cards(matches[1])
            
            if (count_1 == 3 and count_2 == 2) or \
               (count_1 == 3 and count_2 == 3) or \
               (count_1 == 2 and count_2 == 3):
                return True
        
        return False

    # --- QUARANTAINE ET GESTION ---
    def _apply_quarantine(self, prediction: Dict[str, Any]):
        """Applique la quarantaine après un échec - 1 heure"""
        trigger_used = prediction.get('predicted_from_trigger')
        predicted_suit = prediction.get('predicted_costume')
        
        if not trigger_used or not predicted_suit:
            logger.warning("⚠️ Impossible d'appliquer quarantaine: données manquantes")
            return
        
        key = f"{trigger_used}_{predicted_suit}"
        
        for rule in self.smart_rules:
            if rule.get('trigger') == trigger_used and rule.get('predict') == predicted_suit:
                self.quarantined_rules[key] = {
                    'count': rule.get('count', 1),
                    'timestamp': time.time(),
                    'expires_at': time.time() + 3600  # 1 heure
                }
                logger.info(f"🔒 Quarantaine appliquée: {key} (expire dans 1h)")
                break
        
        self.wait_until_next_update = time.time() + 1800  # 30 min cooldown
        self._save_all_data()

    def _mark_rule_as_used(self, trigger: str, suit: str):
        """Marque une règle comme utilisée et la retire des TOP 4"""
        if suit not in self.quarantined_rules:
            self.quarantined_rules[suit] = {}
        
        self.quarantined_rules[suit][trigger] = self.quarantined_rules[suit].get(trigger, 0) + 1
        
        # Mettre à jour les règles actives immédiatement
        self.smart_rules = self._get_active_rules()
        self.last_suit_predictions.append(suit)
        
        self._save_all_data()
        logger.info(f"📝 Règle marquée utilisée et retirée des TOP: {trigger}→{suit}")

    def _check_gap_rule(self, game_num: int) -> bool:
        if self.last_predicted_game_number == 0:
            return True
        gap_ok = game_num >= self.last_predicted_game_number + 3
        logger.debug(f"📏 Vérification écart: J{game_num} >= J{self.last_predicted_game_number}+3 ? {gap_ok}")
        return gap_ok

    def _check_suit_repetition(self, suit: str) -> bool:
        suit_list = list(self.last_suit_predictions)
        count = suit_list.count(suit)
        ok = count < 2
        logger.debug(f"🔄 Vérification anti-répétition {suit}: {count} fois (max 2) -> {ok}")
        return ok

    # --- COMMANDES ET STATUT ---
    def reset_all(self):
        """Réinitialise toutes les données (sauf IDs de canaux)"""
        saved_target = self.target_channel_id
        saved_pred = self.prediction_channel_id
        
        global last_suit_predictions, last_rule_index_by_suit
        last_suit_predictions.clear()
        last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
        
        self.predictions = {}
        self.inter_data = []
        self.smart_rules = []
        self.all_time_rules = []
        self.collected_games = set()
        self.sequential_history = {}
        self.quarantined_rules = {}
        self.last_prediction_time = 0
        self.last_predicted_game_number = 0
        self.last_analysis_time = 0
        self.wait_until_next_update = 0
        self.last_suit_predictions.clear()
        
        self.target_channel_id = saved_target
        self.prediction_channel_id = saved_pred
        self.is_inter_mode_active = False
        
        self._save_all_data()
        logger.info("🔄 RESET COMPLET effectué")

    def get_inter_status(self) -> Tuple[str, Optional[Dict]]:
        """Retourne le statut complet du mode INTER (FORMAT DEMANDÉ)"""
        if not self.is_inter_mode_active:
            msg = "❌ **MODE INTER INACTIF**\n\n"
            msg += f"📊 **{len(self.inter_data)} jeux collectés**\n"
            msg += "⚠️ Pas encore assez de règles créées.\n\n"
            msg += "**Cliquez sur 'Analyser et Activer' pour générer les 16 règles !**"
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': '🔄 Analyser et Activer', 'callback_data': 'inter_apply'}]
                ]
            }
            return msg, keyboard
        
        # Grouper par costume
        rules_by_suit = defaultdict(list)
        for rule in self.smart_rules:
            if isinstance(rule, dict) and 'predict' in rule:
                rules_by_suit[rule['predict']].append(rule)
        
        msg = f"🧠 **MODE INTER - ✅ ACTIF**\n\n"
        msg += f"📊 **{len(self.smart_rules)} règles créées ({len(self.inter_data)} jeux analysés)**\n\n"
        msg += f"🎯 **TOP 4 par enseigne:**\n\n"
        
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            suit_rules = sorted(rules_by_suit.get(suit, []), key=lambda x: (x.get('count', 0), x.get('rank', 0)), reverse=True)
            suit_rules = suit_rules[:4]  # TOP 4
            
            msg += f"**Pour prédire {suit}:**\n"
            
            if suit_rules:
                for rule in suit_rules:
                    trigger = rule.get('trigger', '?')
                    count = rule.get('count', 0)
                    msg += f"  • {trigger} ({count}x)\n"
            else:
                msg += f"  ⚠️ Aucune règle active\n"
            
            # Règles en quarantaine (temporairement masquées)
            if suit in self.quarantined_rules and isinstance(self.quarantined_rules[suit], dict):
                quarantined = self.quarantined_rules[suit]
                if quarantined:
                    msg += f"  _🔒 {len(quarantined)} en quarantaine_\n"
            
            msg += "\n"
        
        # Boutons
        keyboard = {
            'inline_keyboard': [
                [{'text': '🔄 Relancer Analyse', 'callback_data': 'inter_apply'}],
                [{'text': '❌ Désactiver INTER', 'callback_data': 'inter_default'}]
            ]
        }
        
        return msg, keyboard

    def get_collect_info(self) -> str:
        """Génère le message /collect détaillé (FORMAT DEMANDÉ)"""
        msg = f"🧠 **ÉTAT DU MODE INTELLIGENT**\n\n"
        msg += f"Mode: {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}\n"
        msg += f"Données collectées: {len(self.inter_data)} jeux\n"
        msg += f"Règles actives: {len(self.smart_rules)}/16\n\n"
        
        # Grouper par costume
        from collections import Counter
        
        by_trigger = defaultdict(lambda: defaultdict(int))
        for entry in self.inter_data:
            trigger = entry.get('declencheur', '')
            result = entry.get('result_suit', '?')
            trigger_normalized = normalize_card(trigger)
            by_trigger[result][trigger_normalized] += 1
        
        # Afficher les déclencheurs par costume
        msg += "📊 **DÉCLENCHEURS PAR COSTUME:**\n\n"
        
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            if suit in by_trigger:
                triggers = by_trigger[suit]
                msg += f"**{suit}:**\n"
                
                # Trier par fréquence
                sorted_triggers = sorted(triggers.items(), key=lambda x: x[1], reverse=True)
                
                for trigger, count in sorted_triggers:
                    msg += f"  • {trigger} ({count}x)\n"
                
                msg += "\n"
        
        # Statut
        if len(self.inter_data) < 3:
            msg += f"⚠️ **Minimum 3 jeux requis (actuel: {len(self.inter_data)})**\n"
        else:
            msg += f"✅ **OK pour activation INTER**\n"
        
        return msg

# Instance globale SÉCURISÉE
try:
    card_predictor = CardPredictor()
    logger.info("✅ Instance globale CardPredictor créée avec succès")
except Exception as e:
    logger.error(f"❌ ERREUR CRITIQUE lors de la création de card_predictor: {e}")
    logger.error("   Vérifiez que tous les fichiers JSON sont valides")
    card_predictor = None
