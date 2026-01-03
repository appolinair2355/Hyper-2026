# card_predictor.py - VERSION COMPLET CORRIGÉE

import re
import logging
import time
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict, deque
import pytz

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ================== CONFIGURATION ==================
BENIN_TZ = pytz.timezone("Africa/Porto-Novo")

# Règles statiques (13 règles exactes)
STATIC_RULES = {
    "10♦️": "♠️", "10♠️": "❤️", 
    "9♣️": "❤️", "9♦️": "♠️",
    "8♣️": "♠️", "8♠️": "♣️", 
    "7♠️": "♠️", "7♣️": "♣️",
    "6♦️": "♣️", "6♣️": "♦️", 
    "A❤️": "❤️", 
    "5❤️": "❤️", "5♠️": "♠️"
}

# Symboles pour les statuts de vérification
SYMBOL_MAP = {0: '✅0️⃣', 1: '✅1️⃣', 2: '✅2️⃣', 'lost': '❌'}

# Sessions de prédictions
PREDICTION_SESSIONS = [
    (1, 6), (9, 12), (15, 18), (21, 24)
]

class CardPredictor:
    """Gère la logique de prédiction d'ENSEIGNE (Couleur) et la vérification."""

    def __init__(self, telegram_message_sender=None, prediction_channel_id: int = -1003554569009):
        """Initialise le moteur de prédiction avec tous les trackers"""
        
        # IDs des canaux
        self.HARDCODED_SOURCE_ID = -1002682552255
        self.HARDCODED_PREDICTION_ID = prediction_channel_id
        self.prediction_channel_id = prediction_channel_id
        
        # Fonction d'envoi Telegram
        self.telegram_message_sender = telegram_message_sender
        
        # Données de jeu
        self.predictions = {}
        self.processed_messages = set()
        self.last_prediction_time = 0
        self.last_predicted_game_number = 0
        self.consecutive_fails = 0
        self.pending_edits = {}
        
        # Données INTER
        self.sequential_history = {}
        self.inter_data = []
        self.is_inter_mode_active = False
        self.smart_rules = []
        self.last_analysis_time = 0
        self.collected_games = set()
        self.single_trigger_until = 0
        self.quarantined_rules = {}
        self.wait_until_next_update = 0
        self.last_inter_update_time = 0
        self.last_report_sent = {}
        
        # Trackers de performance
        self.trigger_usage_tracker = {}
        self.last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
        self.last_suit_predictions = deque(maxlen=3)
        self.used_rules_cache = {}
        
        # Configuration
        self.config_data = {}
        self.active_admin_chat_id = None
        
        # Cooldown
        self.prediction_cooldown = 30
        
        # Trackers temporaires
        self._last_rule_index = 0
        self._last_trigger_used = None
        
        # Chargement des données sauvegardées
        self._load_all_data()
        
        # Activation automatique si on a des données
        if self.inter_data and not self.is_inter_mode_active and not self.smart_rules:
            self.analyze_and_set_smart_rules(initial_load=True)
        
        logger.info("✅ CardPredictor initialisé avec système de 16 règles dynamiques")

    # =================================================================
    # PERSISTENCE DES DONNÉES
    # =================================================================

    def _get_data_file(self, filename: str) -> str:
        """Retourne le chemin complet du fichier de données"""
        return filename

    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False) -> Any:
        """Charge les données depuis un fichier JSON"""
        try:
            is_dict = filename in ['predictions.json', 'sequential_history.json', 'smart_rules.json', 'pending_edits.json']
            
            if not os.path.exists(filename):
                return set() if is_set else (None if is_scalar else ({} if is_dict else []))
            
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return set() if is_set else (None if is_scalar else ({} if is_dict else []))
                
                data = json.loads(content)
                if is_set:
                    return set(data)
                if isinstance(data, dict) and filename in ['sequential_history.json', 'predictions.json', 'pending_edits.json']:
                    return {int(k): v for k, v in data.items()}
                return data
        
        except Exception as e:
            logger.error(f"⚠️ Erreur chargement {filename}: {e}")
            is_dict = filename in ['predictions.json', 'sequential_history.json', 'smart_rules.json', 'pending_edits.json']
            return set() if is_set else (None if is_scalar else ({} if is_dict else []))

    def _save_data(self, data: Any, filename: str):
        """Sauvegarde les données dans un fichier JSON"""
        try:
            # Convertir les sets en listes
            if isinstance(data, set):
                data = list(data)
            
            # Normaliser les IDs de canaux
            if filename == 'channels_config.json' and isinstance(data, dict):
                if 'target_channel_id' in data and data['target_channel_id'] is not None:
                    data['target_channel_id'] = int(data['target_channel_id'])
                if 'prediction_channel_id' in data and data['prediction_channel_id'] is not None:
                    data['prediction_channel_id'] = int(data['prediction_channel_id'])
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde {filename}: {e}")

    def _load_all_data(self):
        """Charge toutes les données du bot"""
        try:
            self.predictions = self._load_data('predictions.json')
            self.processed_messages = self._load_data('processed.json', is_set=True)
            self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True) or 0
            self.last_predicted_game_number = self._load_data('last_predicted_game_number.json', is_scalar=True) or 0
            self.consecutive_fails = self._load_data('consecutive_fails.json', is_scalar=True) or 0
            self.pending_edits = self._load_data('pending_edits.json')
            
            self.sequential_history = self._load_data('sequential_history.json')
            self.inter_data = self._load_data('inter_data.json')
            self.is_inter_mode_active = self._load_data('inter_mode_status.json', is_scalar=True)
            self.smart_rules = self._load_data('smart_rules.json')
            self.active_admin_chat_id = self._load_data('active_admin_chat_id.json', is_scalar=True)
            self.last_analysis_time = self._load_data('last_analysis_time.json', is_scalar=True) or 0
            self.collected_games = self._load_data('collected_games.json', is_set=True)
            self.single_trigger_until = self._load_data('single_trigger_until.json', is_scalar=True) or 0
            self.quarantined_rules = self._load_data('quarantined_rules.json')
            self.wait_until_next_update = self._load_data('wait_until_next_update.json', is_scalar=True) or 0
            self.last_inter_update_time = self._load_data('last_inter_update.json', is_scalar=True) or 0
            self.last_report_sent = self._load_data('last_report_sent.json')
            
            # Configuration des canaux
            self.config_data = self._load_data('channels_config.json')
            if not self.config_data:
                self.config_data = {}
            
            self.target_channel_id = self.config_data.get('target_channel_id')
            if not self.target_channel_id and self.HARDCODED_SOURCE_ID != 0:
                self.target_channel_id = self.HARDCODED_SOURCE_ID
            
            self.prediction_channel_id = self.config_data.get('prediction_channel_id')
            if not self.prediction_channel_id and self.HARDCODED_PREDICTION_ID != 0:
                self.prediction_channel_id = self.HARDCODED_PREDICTION_ID
            
            # Trackers
            self.trigger_usage_tracker = self._load_data('trigger_usage_tracker.json')
            if not self.trigger_usage_tracker:
                self.trigger_usage_tracker = {}
            
            self.last_rule_index_by_suit = self._load_data('last_rule_index_by_suit.json')
            if not self.last_rule_index_by_suit:
                self.last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
            
            self.used_rules_cache = self._load_data('used_rules_cache.json')
            if not self.used_rules_cache:
                self.used_rules_cache = {}
            
            logger.info(f"📂 Données chargées: {len(self.inter_data)} jeux, {len(self.smart_rules)} règles")
        
        except Exception as e:
            logger.error(f"❌ Erreur chargement données globales: {e}")

    def _save_all_data(self):
        """Sauvegarde toutes les données du bot"""
        try:
            self._save_data(self.predictions, 'predictions.json')
            self._save_data(self.processed_messages, 'processed.json')
            self._save_data(self.last_prediction_time, 'last_prediction_time.json')
            self._save_data(self.last_predicted_game_number, 'last_predicted_game_number.json')
            self._save_data(self.consecutive_fails, 'consecutive_fails.json')
            self._save_data(self.pending_edits, 'pending_edits.json')
            
            self._save_data(self.sequential_history, 'sequential_history.json')
            self._save_data(self.inter_data, 'inter_data.json')
            self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
            self._save_data(self.smart_rules, 'smart_rules.json')
            self._save_data(self.active_admin_chat_id, 'active_admin_chat_id.json')
            self._save_data(self.last_analysis_time, 'last_analysis_time.json')
            self._save_data(self.collected_games, 'collected_games.json')
            self._save_data(self.single_trigger_until, 'single_trigger_until.json')
            self._save_data(self.quarantined_rules, 'quarantined_rules.json')
            self._save_data(self.wait_until_next_update, 'wait_until_next_update.json')
            self._save_data(self.last_inter_update_time, 'last_inter_update.json')
            self._save_data(self.last_report_sent, 'last_report_sent.json')
            self._save_data(self.config_data, 'channels_config.json')
            self._save_data(self.trigger_usage_tracker, 'trigger_usage_tracker.json')
            self._save_data(self.last_rule_index_by_suit, 'last_rule_index_by_suit.json')
            self._save_data(self.used_rules_cache, 'used_rules_cache.json')
            
            logger.debug("💾 Données sauvegardées")
        
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde données globales: {e}")

    # =================================================================
    # GESTION DU TEMPS ET DES SESSIONS
    # =================================================================

    def now(self) -> datetime:
        """Retourne l'heure actuelle au fuseau horaire du Bénin"""
        return datetime.now(BENIN_TZ)

    def is_in_session(self) -> bool:
        """Vérifie si on est dans une session de prédictions"""
        h = self.now().hour
        return any(start <= h < end for start, end in PREDICTION_SESSIONS)

    def current_session_label(self) -> str:
        """Retourne l'étiquette de la session actuelle"""
        h = self.now().hour
        for start, end in PREDICTION_SESSIONS:
            if start <= h < end:
                return f"{start:02d}h00 – {end:02d}h00"
        return "Hors session"

    # =================================================================
    # RAPPORTS DE SESSION
    # =================================================================

    def check_and_send_scheduled_reports(self):
        """Envoie les rapports AUX HEURES EXACTES 6h, 12h, 18h, 00h"""
        if not self.telegram_message_sender or not self.prediction_channel_id:
            return
        
        now = self.now()
        
        # Vérifier si on est pile sur l'heure (marge de 10 secondes)
        if now.minute == 0 and now.second < 10:
            if now.hour in [6, 12, 18, 0]:
                # Clé unique pour éviter les doublons
                key = f"{now.day}_{now.hour}"
                
                if self.last_report_sent.get(key):
                    return
                
                self.last_report_sent[key] = True
                
                # Générer et envoyer le rapport
                report = self.generate_full_report(now)
                self.telegram_message_sender(self.prediction_channel_id, report)
                
                logger.info(f"📊 BILAN ENVOYÉ: {now.hour:02d}h00 pile")
                self._save_all_data()

    def generate_full_report(self, current_time: datetime) -> str:
        """Génère le bilan complet de la session"""
        # Heures de la session
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 
                       18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        start, end = report_hours[current_time.hour]
        
        # Statistiques
        session_predictions = {k: v for k, v in self.predictions.items() 
                              if v.get('status') in ['won', 'lost', 'pending']}
        total = len(session_predictions)
        wins = sum(1 for p in session_predictions.values() if p.get('status') == 'won')
        fails = sum(1 for p in session_predictions.values() if p.get('status') == 'lost')
        
        # Règles en quarantaine
        total_quarantined = sum(len(q) for q in self.quarantined_rules.values())
        
        report = (
            f"📊 **BILAN HORAIRE - {current_time.strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
            f"🎯 Session: {start} – {end}\n"
            f"🧠 Mode: {'✅ INTER ACTIF' if self.is_inter_mode_active else '❌ STATIQUE'}\n"
            f"🔄 Règles actives: {len(self.smart_rules)}/16 | Quarantaine: {total_quarantined}\n\n"
            f"📈 **RÉSULTATS**\n"
            f"Total: {total} | ✅ {wins} | ❌ {fails}\n\n"
            f"👨‍💻 Dev: Sossou Kouamé\n"
            f"🎟️ Code: Koua229"
        )
        
        return report

    def get_session_report_preview(self) -> str:
        """Retourne un aperçu du prochain rapport"""
        now = self.now()
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 
                       18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        
        # Prochaine heure de rapport
        next_report_hour = None
        for h in sorted(report_hours.keys()):
            if h > now.hour:
                next_report_hour = h
                break
        if next_report_hour is None:
            next_report_hour = min(report_hours.keys())
        
        # Temps restant
        minutes_until = ((next_report_hour - now.hour) * 60 - now.minute) % (24 * 60)
        hours = minutes_until // 60
        mins = minutes_until % 60
        start, end = report_hours[next_report_hour]
        
        # Stats
        session_predictions = {k: v for k, v in self.predictions.items() 
                              if v.get('status') in ['won', 'lost', 'pending']}
        total = len(session_predictions)
        wins = sum(1 for p in session_predictions.values() if p.get('status') == 'won')
        
        msg = (
            f"📋 **APERÇU DU BILAN**\n\n"
            f"⏰ Heure: {now.strftime('%H:%M:%S - %d/%m/%Y')}\n"
            f"🎯 Prochain bilan: {start} – {end}\n"
            f"⏳ Temps restant: {hours}h{mins:02d}\n\n"
            f"🧠 Mode: {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}\n"
            f"📊 Stats: {total} prédictions | ✅ {wins} réussites"
        )
        
        return msg

    def set_channel_id(self, channel_id: int, channel_type: str) -> bool:
        """Définit un canal comme source ou prédiction"""
        if not isinstance(self.config_data, dict):
            self.config_data = {}
        
        if channel_type == 'source':
            self.target_channel_id = channel_id
            self.config_data['target_channel_id'] = channel_id
        elif channel_type == 'prediction':
            self.prediction_channel_id = channel_id
            self.config_data['prediction_channel_id'] = channel_id
        
        self._save_data(self.config_data, 'channels_config.json')
        logger.info(f"✅ Canal {channel_type} défini: {channel_id}")
        return True

    # =================================================================
    # EXTRACTION ET ANALYSE DES MESSAGES
    # =================================================================

    def _extract_parentheses_content(self, text: str) -> List[str]:
        """Extrait le contenu de toutes les sections de parenthèses"""
        pattern = r'\(([^)]+)\)'
        return re.findall(pattern, text)

    def extract_game_number(self, message: str) -> Optional[int]:
        """Extrait le numéro de jeu du message"""
        match = re.search(r'#N(\d+)\.', message, re.IGNORECASE)
        if not match:
            match = re.search(r'🔵(\d+)🔵', message)
        
        if match:
            num = int(match.group(1))
            logger.debug(f"🎮 Numéro du jeu extrait: {num}")
            return num
        
        return None

    def extract_game_number_from_text(self, text: str) -> Optional[int]:
        """Extrait le numéro de jeu avec plus de robustesse"""
        patterns = [
            r'#N(\d+)\.',
            r'🔵(\d+)🔵',
            r'Jeu\s*(\d+)',
            r'J\s*(\d+)',
            r'GAME\s*(\d+)',
            r'N°\s*(\d+)',
            r'#(\d+)',
            r'\b(\d{1,4})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                if 1 <= num <= 9999:
                    return num
        
        return None

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        """Compte les cartes dans une chaîne"""
        normalized_content = content.replace("❤️", "♥️")
        return re.findall(r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)', normalized_content, re.IGNORECASE)

    def get_first_card_info(self, message: str) -> Optional[Tuple[str, str]]:
        """Retourne la PREMIÈRE carte du PREMIER groupe"""
        match = re.search(r'\(([^)]*)\)', message)
        if not match:
            return None
        
        details = self.extract_card_details(match.group(1))
        if details:
            v, c = details[0]
            if c == "♥️":
                c = "❤️"
            return f"{v.upper()}{c}", c
        
        return None

    def get_all_cards_in_first_group(self, message: str) -> List[str]:
        """Retourne TOUTES les cartes du PREMIER groupe"""
        match = re.search(r'\(([^)]*)\)', message)
        if not match:
            return []
        
        details = self.extract_card_details(match.group(1))
        cards = []
        for v, c in details:
            normalized_c = "♥️" if c == "❤️" else c
            cards.append(f"{v.upper()}{normalized_c}")
        
        return cards

    def get_all_cards_in_second_group(self, message: str) -> List[str]:
        """Retourne TOUTES les cartes du SECOND groupe (optionnel)"""
        matches = re.findall(r'\([^)]*\)', message)
        if len(matches) < 2:
            return []
        
        details = self.extract_card_details(matches[1])
        cards = []
        for v, c in details:
            normalized_c = "♥️" if c == "❤️" else c
            cards.append(f"{v.upper()}{normalized_c}")
        
        return cards

    def has_pending_indicators(self, text: str) -> bool:
        """Vérifie si le message contient des indicateurs de message temporaire"""
        indicators = ['⏰', '▶', '🕐', '➡️', '...']
        return any(indicator in text for indicator in indicators)

    def has_completion_indicators(self, text: str) -> bool:
        """Vérifie si le message est finalisé (✅ ou 🔰)"""
        completion_indicators = ['✅', '🔰']
        return any(indicator in text for indicator in completion_indicators)

    def is_final_result_structurally_valid(self, text: str) -> bool:
        """Vérifie si la structure correspond à un résultat final"""
        matches = self._extract_parentheses_content(text)
        num_sections = len(matches)
        
        if num_sections < 1:
            return False
        
        # Si c'est un message avec ✅ ou 🔰, c'est forcément final
        if self.has_completion_indicators(text):
            return True
        
        # Vérifier le format standard (2 groupes)
        if num_sections >= 2:
            content_1 = matches[0]
            content_2 = matches[1]
            count_1 = len(self.extract_card_details(content_1))
            count_2 = len(self.extract_card_details(content_2))
            
            # Formats acceptés: 3/2, 3/3, 2/3, 2/2
            if (count_1 == 3 and count_2 in [2, 3]) or (count_1 == 2 and count_2 in [2, 3]):
                return True
        
        return False

    def check_costume_in_first_parentheses(self, message: str, predicted_costume: str) -> bool:
        """
        Vérifie si le costume prédit est dans AU MOINS UNE carte du PREMIER groupe
        """
        try:
            all_cards = self.get_all_cards_in_first_group(message)
            
            if not all_cards:
                logger.debug("🎯 Aucune carte trouvée dans le premier groupe")
                return False
            
            # Normaliser les costumes
            predicted_normalized = predicted_costume.replace("❤️", "♥️")
            
            for card in all_cards:
                # Extraire l'enseigne de la carte
                for suit in ["♠️", "♥️", "♦️", "♣️"]:
                    if suit in card:
                        card_suit = suit
                        break
                else:
                    continue
                
                # Comparer
                if card_suit == predicted_normalized:
                    logger.debug(f"✅ Costume {predicted_normalized} trouvé dans {card}")
                    return True
            
            logger.debug(f"❌ Costume {predicted_normalized} non trouvé dans {all_cards}")
            return False
        
        except Exception as e:
            logger.error(f"❌ Erreur check costume: {e}")
            return False

    # =================================================================
    # COLLECTE DES DONNÉES POUR LE MODE INTER
    # =================================================================

    def collect_inter_data(self, game_number: int, message: str):
        """Collecte les données (N-2 -> N) même sur messages temporaires"""
        info = self.get_first_card_info(message)
        if not info:
            return
        
        full_card, suit = info
        result_suit_normalized = suit.replace("❤️", "♥️")
        
        # Vérifier si déjà collecté
        if game_number in self.collected_games:
            existing = self.sequential_history.get(game_number)
            if existing and existing.get('carte') == full_card:
                logger.debug(f"🧠 Jeu {game_number} déjà collecté, ignoré.")
                return
        
        self.sequential_history[game_number] = {'carte': full_card, 'date': datetime.now().isoformat()}
        self.collected_games.add(game_number)
        
        n_minus_2 = game_number - 2
        trigger_entry = self.sequential_history.get(n_minus_2)
        
        if trigger_entry:
            trigger_card = trigger_entry['carte']
            entry = {
                'numero_resultat': game_number,
                'declencheur': trigger_card,
                'numero_declencheur': n_minus_2,
                'result_suit': result_suit_normalized,
                'date': datetime.now().isoformat()
            }
            self.inter_data.append(entry)
            logger.info(f"🧠 Jeu {game_number} collecté: {trigger_card} → {result_suit_normalized}")
        
        # Nettoyage anciennes données
        limit = game_number - 50
        self.sequential_history = {k: v for k, v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        
        self._save_all_data()

    # =================================================================
    # ANALYSE ET CRÉATION DES RÈGLES (16 RÈGLES DYNAMIQUES)
    # =================================================================

    def analyze_and_set_smart_rules(self, chat_id: Optional[int] = None, 
                                   initial_load: bool = False, 
                                   force_activate: bool = False):
        """Analyse les données et crée EXACTEMENT 16 règles avec système de quarantaine"""
        
        logger.info("🔍 DÉBUT ANALYSE - Création des 16 règles dynamiques...")
        
        # 1. Groupement par enseigne de résultat
        result_suit_groups = defaultdict(lambda: defaultdict(int))
        
        for entry in self.inter_data:
            trigger_card = entry['declencheur']
            result_suit = entry['result_suit']
            
            # Normaliser les costumes
            result_normalized = result_suit.replace("♥️", "❤️")
            
            # Compter les occurrences
            result_suit_groups[result_normalized][trigger_card] += 1
        
        # 2. Créer toutes les règles (TOP illimité)
        all_rules = []
        for result_suit in ['♠️', '❤️', '♦️', '♣️']:
            triggers = result_suit_groups.get(result_suit, {})
            
            # Trier par fréquence
            sorted_triggers = sorted(triggers.items(), key=lambda x: x[1], reverse=True)
            
            for rank, (trigger, count) in enumerate(sorted_triggers, 1):
                all_rules.append({
                    'trigger': trigger,
                    'predict': result_suit,
                    'count': count,
                    'rank': rank
                })
        
        # 3. Mettre à jour la base complète
        self.all_time_rules = all_rules
        
        # 4. Sélectionner les 16 règles actives (hors quarantaine)
        self.smart_rules = self._get_active_rules()
        
        # 5. Réinitialiser les trackers
        self.used_rules_cache = {}
        self.last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
        
        if force_activate:
            self.is_inter_mode_active = True
            if chat_id:
                self.active_admin_chat_id = chat_id
        
        self.last_inter_update_time = time.time()
        self._save_all_data()
        
        logger.info(f"✅ ANALYSE TERMINÉE: {len(self.smart_rules)} règles actives créées")
        
        # 6. Notification
        if chat_id and self.telegram_message_sender:
            self._send_inter_status(chat_id)

    def _get_active_rules(self) -> List[Dict]:
        """Sélectionne les 16 règles actives (4 par costume, hors quarantaine)"""
        active_rules = []
        
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            # Récupérer toutes les règles pour ce costume
            suit_rules = [r for r in self.all_time_rules if r.get('predict') == suit]
            
            # Filtrer la quarantaine
            quarantined = self.quarantined_rules.get(suit, {})
            available = [r for r in suit_rules if r['trigger'] not in quarantined]
            
            # Si moins de 4 disponibles, reprendre les moins utilisées de la quarantaine
            if len(available) < 4 and quarantined:
                # Trier par nombre d'utilisations croissant
                sorted_quarantined = sorted(quarantined.items(), key=lambda x: x[1])
                triggers_to_restore = [t for t, count in sorted_quarantined[:4-len(available)]]
                
                # Les retirer de la quarantaine
                for trigger in triggers_to_restore:
                    if trigger in self.quarantined_rules.get(suit, {}):
                        del self.quarantined_rules[suit][trigger]
                        logger.info(f"🔄 Règle {trigger}→{suit} retirée de la quarantaine")
                
                # Reconstruire la liste disponible
                available = [r for r in suit_rules if r['trigger'] not in self.quarantined_rules.get(suit, {})]
            
            # Prendre les 4 premières
            active_rules.extend(available[:4])
        
        return active_rules

    def _send_inter_status(self, chat_id: int):
        """Envoie le statut détaillé du mode INTER"""
        if not self.telegram_message_sender:
            return
        
        msg, kb = self.get_inter_status()
        self.telegram_message_sender(chat_id, msg, reply_markup=kb)

    def check_and_update_rules(self):
        """Mise à jour périodique (30 minutes)"""
        if time.time() - self.last_analysis_time > 1800:
            logger.info("🔄 Mise à jour INTER périodique (30 min)")
            if len(self.inter_data) >= 3:
                self.analyze_and_set_smart_rules(chat_id=self.active_admin_chat_id, force_activate=True)
            else:
                self.analyze_and_set_smart_rules(chat_id=self.active_admin_chat_id)

    # =================================================================
    # VÉRIFICATION DES PRÉDICTIONS (CRITIQUE - CORRIGÉ)
    # =================================================================

    def _create_status_message(self, game_num: int, offset: int, predicted_suit: str, result: str) -> str:
        """Crée le message de statut avec emojis"""
        if result == 'won':
            status_symbol = f"✅{offset}️⃣"
        else:
            status_symbol = "❌"
        
        return f"🔵{game_num}🔵:{predicted_suit} statut :{status_symbol}"

    def _verify_prediction_common(self, text: str) -> Optional[Dict]:
        """
        Vérifie les prédictions en attente contre un message finalisé
        CETTE FONCTION EST CRITIQUE - elle est appelée pour chaque message
        """
        try:
            # Vérifier si le message est finalisé
            if not self.has_completion_indicators(text):
                logger.debug("⏭️ Message non finalisé, ignoré")
                return None
            
            # Extraire le numéro de jeu
            current_game = self.extract_game_number_from_text(text)
            if not current_game:
                logger.debug("❌ Numéro de jeu non trouvé")
                return None
            
            logger.info(f"🔍 VÉRIFICATION JEU {current_game}")
            
            # Parcourir les prédictions en attente
            for pred_game_num, prediction in list(self.predictions.items()):
                if prediction.get('status') != 'pending':
                    continue
                
                # Vérifier les 3 offsets
                for offset in [0, 1, 2]:
                    expected_game = int(pred_game_num) + offset
                    
                    if current_game == expected_game:
                        predicted_suit = prediction.get('predicted_costume')
                        
                        # Vérifier si le costume est dans le premier groupe
                        if self.check_costume_in_first_parentheses(text, predicted_suit):
                            # ✅ VICTOIRE à l'offset
                            status_symbol = f"✅{offset}️⃣"
                            logger.info(f"✅ SUCCÈS: J{pred_game_num}+{offset} → {predicted_suit}")
                            
                            # Mettre à jour la prédiction
                            self.predictions[pred_game_num]['status'] = 'won'
                            self.predictions[pred_game_num]['verification_offset'] = offset
                            
                            # Préparer la mise à jour
                            updated_message = self._create_status_message(
                                int(pred_game_num), offset, predicted_suit, 'won'
                            )
                            
                            self._save_all_data()
                            
                            return {
                                'type': 'edit_message',
                                'message_id_to_edit': prediction.get('message_id'),
                                'new_message': updated_message,
                                'game_num': pred_game_num,
                                'offset': offset,
                                'result': 'won'
                            }
                        
                        # Si on est à l'offset 2 et pas trouvé = DÉFAITE
                        if offset == 2:
                            status_symbol = "❌"
                            logger.info(f"❌ ÉCHEC: J{pred_game_num} → {predicted_suit} non trouvé")
                            
                            self.predictions[pred_game_num]['status'] = 'lost'
                            self.predictions[pred_game_num]['verification_offset'] = 2
                            
                            updated_message = self._create_status_message(
                                int(pred_game_num), 2, predicted_suit, 'lost'
                            )
                            
                            # QUARANTAINE si mode INTER
                            if prediction.get('is_inter'):
                                self._apply_quarantine(prediction)
                            
                            self._save_all_data()
                            
                            return {
                                'type': 'edit_message',
                                'message_id_to_edit': prediction.get('message_id'),
                                'new_message': updated_message,
                                'game_num': pred_game_num,
                                'offset': 2,
                                'result': 'lost'
                            }
            
            return None
        
        except Exception as e:
            logger.error(f"❌ Erreur vérification: {e}", exc_info=True)
            return None

    def verify_prediction(self, message: str) -> Optional[Dict]:
        """Alias pour messages normaux"""
        return self._verify_prediction_common(message)

    def verify_prediction_from_edit(self, message: str) -> Optional[Dict]:
        """Alias pour messages édités"""
        return self._verify_prediction_common(message)

    # =================================================================
    # PRÉDICTIONS AUTOMATIQUES ET MANUELLES
    # =================================================================

    def check_and_send_automatic_predictions(self):
        """DÉSACTIVÉ - Les prédictions sont gérées uniquement par le canal source"""
        pass

    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str], Optional[bool]]:
        """
        Détermine si on doit prédire (manuel)
        PRIORITÉ ABSOLUE au contenu entre parenthèses
        """
        self.check_and_send_reports()
        self.check_and_update_rules()
        
        if not self.is_in_session():
            logger.debug(f"⚠️ Hors session. Heure: {self.now().hour}h")
            return False, None, None, None
        
        # Vérifier si une prédiction est déjà en attente
        if any(p.get('status') == 'pending' for p in self.predictions.values()):
            logger.debug("⚠️ Prédiction déjà en attente")
            return False, None, None, None
        
        # Vérifier cooldown
        if time.time() < self.wait_until_next_update:
            logger.debug("⏸️ Cooldown actif")
            return False, None, None, None
        
        # Extraire numéro de jeu
        game_number = self.extract_game_number(message)
        if not game_number:
            logger.debug("❌ Numéro de jeu non trouvé")
            return False, None, None, None
        
        # Vérifier écart
        if self.last_predicted_game_number and (game_number - self.last_predicted_game_number < 3):
            logger.debug(f"⏳ Écart insuffisant: {game_number - self.last_predicted_game_number} < 3")
            return False, None, None, None
        
        # EXTRACTION PRIORITAIRE des parenthèses
        parent_content = self._extract_parentheses_content(message)
        if parent_content and len(parent_content) > 0:
            first_group = parent_content[0]
            logger.info(f"📌 Contenu parenthèses: {first_group}")
            
            # Chercher dans les règles intelligentes
            if self.is_inter_mode_active and self.smart_rules:
                for rule in self.smart_rules:
                    if rule['trigger'] in first_group:
                        predicted_suit = rule['predict']
                        self._last_trigger_used = rule['trigger']
                        self._last_rule_index = rule.get('rank', 1) - 1
                        return True, game_number, predicted_suit, True
            
            # Chercher dans les règles statiques
            if not self.is_inter_mode_active:
                cards = self.get_all_cards_in_first_group(message)
                for card in cards:
                    if card in STATIC_RULES:
                        predicted_suit = STATIC_RULES[card]
                        self._last_trigger_used = card
                        return True, game_number, predicted_suit, False
        
        return False, None, None, None

    def prepare_prediction_text(self, game_number_source: int, predicted_costume: str) -> str:
        """Prépare le texte de prédiction"""
        target_game = game_number_source + 2
        text = f"🔵{target_game}🔵:{predicted_costume} statut :⏳"
        logger.info(f"📝 Prédiction: J{game_number_source} → J{target_game}, Costume: {predicted_costume}")
        return text

    def make_prediction(self, game_number_source: int, suit: str, message_id_bot: int,
                       is_inter: bool = False, trigger_used: Optional[str] = None):
        """Enregistre une prédiction dans le système"""
        target = game_number_source + 2
        
        # Obtenir le déclencheur
        if not trigger_used:
            trigger_used = self._last_trigger_used or '?'
        
        # Déterminer l'index de règle
        rule_index = self._last_rule_index if is_inter else 0
        
        self.predictions[str(target)] = {
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
        self.consecutive_fails = 0
        
        # Marquer la règle comme utilisée
        if is_inter:
            self._mark_rule_as_used(trigger_used, suit)
        
        self._save_all_data()
        logger.info(f"🎯 Prédiction enregistrée: J{target} → {suit} (trigger: {trigger_used})")

    # =================================================================
    # QUARANTAINE ET GESTION DES RÈGLES
    # =================================================================

    def _apply_quarantine(self, prediction: Dict[str, Any]):
        """Applique la quarantaine après un échec - 1 heure"""
        trigger_used = prediction.get('predicted_from_trigger')
        predicted_suit = prediction.get('predicted_costume')
        
        if not trigger_used or not predicted_suit:
            return
        
        if predicted_suit not in self.quarantined_rules:
            self.quarantined_rules[predicted_suit] = {}
        
        self.quarantined_rules[predicted_suit][trigger_used] = 1
        
        # Mettre à jour les règles actives
        self.smart_rules = self._get_active_rules()
        
        logger.info(f"🔒 Quarantaine: {trigger_used}→{predicted_suit}")
        self._save_all_data()

    def _mark_rule_as_used(self, trigger: str, suit: str):
        """Marque une règle comme utilisée pour ce cycle"""
        if suit not in self.used_rules_cache:
            self.used_rules_cache[suit] = []
        
        self.used_rules_cache[suit].append(trigger)
        self.last_suit_predictions.append(suit)
        
        # Mettre à jour les règles actives
        self.smart_rules = self._get_active_rules()
        
        self._save_all_data()
        logger.debug(f"📝 Règle marquée comme utilisée: {trigger}→{suit}")

    def _check_gap_rule(self, game_num: int) -> bool:
        """Vérifie l'écart strict de 3 entre prédictions"""
        if self.last_predicted_game_number == 0:
            return True
        return game_num >= self.last_predicted_game_number + 3

    def _check_suit_repetition(self, suit: str) -> bool:
        """Vérifie qu'on ne dépasse pas 2 répétitions consécutives"""
        suit_list = list(self.last_suit_predictions)
        count = suit_list.count(suit)
        return count < 2

    def _get_next_available_rule(self, suit: str) -> Tuple[Optional[Dict], Optional[int]]:
        """Récupère la prochaine règle disponible (round-robin)"""
        if suit not in self.last_rule_index_by_suit:
            self.last_rule_index_by_suit[suit] = 0
        
        # Filtrer les règles pour ce costume
        suit_rules = [r for r in self.smart_rules if r.get('predict') == suit]
        
        if len(suit_rules) < 4:
            logger.warning(f"⚠️ Seulement {len(suit_rules)} règles pour {suit}")
            return None, None
        
        # Round-robin
        start_index = self.last_rule_index_by_suit[suit]
        for i in range(4):
            idx = (start_index + i) % len(suit_rules)
            rule = suit_rules[idx]
            trigger = rule.get('trigger')
            
            if trigger not in self.used_rules_cache.get(suit, []):
                self.last_rule_index_by_suit[suit] = idx
                return rule, idx
        
        logger.info(f"🔄 Toutes les règles {suit} utilisées ce cycle")
        return None, None

    # =================================================================
    # COMMANDES ET STATUT
    # =================================================================

    def reset_all(self):
        """Réinitialise toutes les données (sauf IDs de canaux)"""
        saved_target = self.target_channel_id
        saved_pred = self.prediction_channel_id
        
        # Réinitialiser les trackers globaux
        global last_suit_predictions, last_rule_index_by_suit
        last_suit_predictions.clear()
        last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
        
        # Réinitialiser toutes les données
        self.predictions = {}
        self.inter_data = []
        self.smart_rules = []
        self.all_time_rules = []
        self.collected_games = set()
        self.sequential_history = {}
        self.quarantined_rules = {}
        self.pending_edits = {}
        self.last_report_sent = {}
        self.last_prediction_time = 0
        self.last_predicted_game_number = 0
        self.consecutive_fails = 0
        self.last_analysis_time = 0
        self.single_trigger_until = 0
        self.wait_until_next_update = 0
        self.last_inter_update_time = 0
        self.trigger_usage_tracker = {}
        self.used_rules_cache = {}
        self.last_suit_predictions.clear()
        
        # Restaurer les IDs
        self.target_channel_id = saved_target
        self.prediction_channel_id = saved_pred
        self.is_inter_mode_active = False
        
        self._save_all_data()
        logger.info("🔄 RESET COMPLET effectué")

    def get_inter_status(self) -> Tuple[str, Optional[Dict]]:
        """Retourne le statut complet du mode INTER"""
        if not self.is_inter_mode_active:
            msg = "❌ **MODE INTER INACTIF**\nUtilisez `/inter activate` pour activer."
            return msg, None
        
        # Forcer la mise à jour des règles actives
        self.smart_rules = self._get_active_rules()
        
        msg = f"🧠 **MODE INTER - ✅ ACTIF**\n\n"
        msg += f"📊 {len(self.smart_rules)}/16 règles actives ({len(self.inter_data)} jeux)\n\n"
        
        # Afficher les TOP 4 par costume
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            suit_rules = [r for r in self.smart_rules if r.get('predict') == suit]
            
            msg += f"**Pour prédire {suit}:**\n"
            
            if suit_rules:
                for idx, rule in enumerate(suit_rules, 1):
                    trigger = rule.get('trigger', '?')
                    count = rule.get('count', 0)
                    msg += f"  • {trigger} ({count}x)\n"
            
            # Règles en quarantaine
            quarantined = self.quarantined_rules.get(suit, {})
            if quarantined:
                msg += f"  _🔒 Quarantaine: {len(quarantined)} règle(s)_\n"
            
            msg += "\n"
        
        # Info round-robin
        msg += "🔄 **Rotation Round-Robin:**\n"
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            next_idx = self.last_rule_index_by_suit.get(suit, 0) + 1
            msg += f"  {suit}: Prochain TOP{next_idx}\n"
        
        # Boutons
        kb = {
            'inline_keyboard': [[
                {'text': '🔄 Relancer Analyse', 'callback_data': 'inter_apply'},
                {'text': '❌ Désactiver', 'callback_data': 'inter_default'}
            ]]
        }
        
        return msg, kb

    def get_collect_info(self) -> str:
        """Génère le message /collect détaillé"""
        msg = f"🧠 **ÉTAT DU MODE INTELLIGENT**\n\n"
        msg += f"Mode: {'✅ ACTIF' if self.is_inter_mode_active else '❌ INACTIF'}\n"
        msg += f"Données collectées: {len(self.inter_data)} jeux\n"
        msg += f"Règles actives: {len(self.smart_rules)}/16\n\n"
        
        # Grouper par costume
        from collections import Counter
        
        by_result_suit = defaultdict(list)
        for entry in self.inter_data:
            result_suit = entry.get('result_suit', '?')
            trigger = entry.get('declencheur', '')
            
            # Extraction parenthèses prioritaire
            parent_content = self._extract_parentheses_content(trigger)
            if parent_content:
                trigger = parent_content[0] if isinstance(parent_content, list) else str(parent_content)
            
            by_result_suit[result_suit].append(trigger)
        
        # Afficher avec comptes
        msg += "📊 **TOUS LES DÉCLENCHEURS:**\n\n"
        
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            if suit in by_result_suit:
                triggers = by_result_suit[suit]
                msg += f"**{suit}:** {len(triggers)} occurrences\n"
                
                # Compter et marquer les utilisés
                quarantined = self.quarantined_rules.get(suit, {})
                trigger_counts = Counter(triggers).most_common()
                
                for trigger, count in trigger_counts:
                    used_count = quarantined.get(trigger, 0)
                    if used_count > 0:
                        msg += f"  • 🔒 {trigger} ({count}x total, {used_count}x utilisé)\n"
                    else:
                        msg += f"  • ✅ {trigger} ({count}x)\n"
                
                msg += "\n"
        
        if len(self.inter_data) < 3:
            msg += f"⚠️ Minimum 3 jeux requis (actuel: {len(self.inter_data)})\n"
        
        return msg

# Instance globale
card_predictor = CardPredictor()

