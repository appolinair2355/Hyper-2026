# 1️⃣ FICHIER: card_predictor.py (CODE COMPLET CORRIGÉ)

import re
import logging
import time
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict, deque, Counter
import pytz

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ================== CONFIGURATION ==================
BENIN_TZ = pytz.timezone("Africa/Porto-Novo")
PREDICTION_CHANNEL_ID = -1003554569009  # ✅ NOUVEL ID DU CANAL

# Règles statiques (utilisées UNIQUEMENT si mode INTER désactivé)
STATIC_RULES = {
    "10♦️": "♠️", "10♠️": "❤️", "9♣️": "❤️", "9♦️": "♠️",
    "8♣️": "♠️", "8♠️": "♣️", "7♠️": "♠️", "7♣️": "♣️",
    "6♦️": "♣️", "6♣️": "♦️", "A❤️": "❤️", "5❤️": "❤️", "5♠️": "♠️"
}

# Sessions de prédictions
PREDICTION_SESSIONS = [(1, 6), (9, 12), (15, 18), (21, 24)]

# Trackers globaux pour la rotation
last_suit_predictions = deque(maxlen=3)
last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}

class CardPredictor:
    def __init__(self, telegram_message_sender=None, prediction_channel_id: int = PREDICTION_CHANNEL_ID):
        """Initialise le moteur de prédiction avec tous les trackers"""
        
        # IDs des canaux
        self.HARDCODED_SOURCE_ID = -1002682552255
        self.HARDCODED_PREDICTION_ID = prediction_channel_id
        
        # Fonction d'envoi Telegram
        self.telegram_message_sender = telegram_message_sender
        
        # Données de jeu
        self.predictions = {}
        self.inter_data = []
        self.collected_games = set()
        self.sequential_history = {}
        
        # Règles intelligentes (16 règles)
        self.smart_rules = []
        self.all_time_rules = []
        self.quarantined_rules = {}
        
        # Trackers de performance
        self.trigger_usage_tracker = {}
        self.last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
        self.last_suit_predictions = deque(maxlen=3)
        self.used_rules_cache = {}
        
        # Timing
        self.last_prediction_time = 0
        self.last_predicted_game_number = 0
        self.last_analysis_time = 0
        self.wait_until_next_update = 0
        
        # Bilans horaires
        self.bilan_times = [6, 12, 18, 0]
        self.last_bilan_sent = None
        
        # Mode et statut
        self.is_inter_mode_active = False
        self._last_trigger_used = None
        self._last_rule_index_used = None
        
        # Chargement des données
        self._load_all_data()
        
        # Activation auto si données disponibles
        if self.inter_data and not self.is_inter_mode_active:
            self.analyze_and_set_smart_rules(initial_load=True)
        
        logger.info("✅ CardPredictor initialisé avec système 16 règles + écart 3")

    # =================================================================
    # PERSISTENCE
    # =================================================================

    def _get_data_file(self, filename: str) -> str:
        return filename

    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False) -> Any:
        try:
            is_dict = filename in ['predictions.json', 'sequential_history.json', 'smart_rules.json', 'quarantined_rules.json']
            
            if not os.path.exists(filename):
                return set() if is_set else (None if is_scalar else ({} if is_dict else []))
            
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return set() if is_set else (None if is_scalar else ({} if is_dict else []))
                
                data = json.loads(content)
                if is_set:
                    return set(data)
                if isinstance(data, dict) and filename in ['sequential_history.json', 'predictions.json']:
                    return {int(k): v for k, v in data.items()}
                return data
        
        except Exception as e:
            logger.error(f"⚠️ Erreur chargement {filename}: {e}")
            is_dict = filename in ['predictions.json', 'sequential_history.json', 'smart_rules.json', 'quarantined_rules.json']
            return set() if is_set else (None if is_scalar else ({} if is_dict else []))

    def _save_data(self, data: Any, filename: str):
        try:
            if isinstance(data, set):
                data = list(data)
            
            if filename == 'channels_config.json' and isinstance(data, dict):
                for key in ['target_channel_id', 'prediction_channel_id']:
                    if key in data and data[key] is not None:
                        data[key] = int(data[key])
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde {filename}: {e}")

    def _load_all_data(self):
        """Charge toutes les données du bot"""
        try:
            # Données principales
            self.predictions = self._load_data('predictions.json')
            self.inter_data = self._load_data('inter_data.json')
            self.collected_games = self._load_data('collected_games.json', is_set=True)
            self.sequential_history = self._load_data('sequential_history.json')
            self.smart_rules = self._load_data('smart_rules.json')
            self.all_time_rules = self._load_data('all_time_rules.json')
            self.quarantined_rules = self._load_data('quarantined_rules.json')
            
            # Trackers
            self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True) or 0
            self.last_predicted_game_number = self._load_data('last_predicted_game_number.json', is_scalar=True) or 0
            self.last_analysis_time = self._load_data('last_analysis_time.json', is_scalar=True) or 0
            self._last_trigger_used = self._load_data('last_trigger_used.json', is_scalar=True)
            self._last_rule_index = self._load_data('last_rule_index.json', is_scalar=True) or 0
            
            # Configuration
            self.config_data = self._load_data('channels_config.json')
            if not self.config_data:
                self.config_data = {}
            
            self.target_channel_id = self.config_data.get('target_channel_id') or self.HARDCODED_SOURCE_ID
            self.prediction_channel_id = self.config_data.get('prediction_channel_id') or self.HARDCODED_PREDICTION_ID
            
            logger.info(f"📂 Données chargées: {len(self.inter_data)} jeux, {len(self.smart_rules)} règles")
        
        except Exception as e:
            logger.error(f"❌ Erreur chargement données globales: {e}")

    def _save_all_data(self):
        """Sauvegarde toutes les données du bot"""
        try:
            # Données principales
            self._save_data(self.predictions, 'predictions.json')
            self._save_data(self.inter_data, 'inter_data.json')
            self._save_data(self.collected_games, 'collected_games.json')
            self._save_data(self.sequential_history, 'sequential_history.json')
            self._save_data(self.smart_rules, 'smart_rules.json')
            self._save_data(self.all_time_rules, 'all_time_rules.json')
            self._save_data(self.quarantined_rules, 'quarantined_rules.json')
            
            # Trackers
            self._save_data(self.last_prediction_time, 'last_prediction_time.json')
            self._save_data(self.last_predicted_game_number, 'last_predicted_game_number.json')
            self._save_data(self.last_analysis_time, 'last_analysis_time.json')
            self._save_data(self._last_trigger_used, 'last_trigger_used.json')
            self._save_data(self._last_rule_index, 'last_rule_index.json')
            
            logger.debug("💾 Données sauvegardées")
        
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde données globales: {e}")

    # =================================================================
    # TEMPS ET SESSIONS
    # =================================================================

    def now(self) -> datetime:
        return datetime.now(BENIN_TZ)

    def is_in_session(self) -> bool:
        h = self.now().hour
        return any(start <= h < end for start, end in PREDICTION_SESSIONS)

    def current_session_label(self) -> str:
        h = self.now().hour
        for start, end in PREDICTION_SESSIONS:
            if start <= h < end:
                return f"{start:02d}h00 – {end:02d}h00"
        return "Hors session"

    # =================================================================
    # BILANS HORAIRES STRICTS
    # =================================================================

    def check_and_send_scheduled_reports(self):
        """Envoie les bilans AUX HEURES EXACTES 6h, 12h, 18h, 00h"""
        if not self.telegram_message_sender or not self.prediction_channel_id:
            return
        
        now = self.now()
        
        # Vérifier si on est pile sur l'heure (marge 10s)
        if now.minute == 0 and now.second < 10:
            if now.hour in self.bilan_times:
                key = f"{now.day}_{now.hour}"
                
                if self.last_report_sent and self.last_report_sent.get(key):
                    return
                
                if not self.last_report_sent:
                    self.last_report_sent = {}
                
                self.last_report_sent[key] = True
                
                # Générer et envoyer le rapport
                report = self.generate_full_report(now)
                self.telegram_message_sender(self.prediction_channel_id, report)
                
                logger.info(f"📊 BILAN ENVOYÉ: {now.hour:02d}h00 pile")
                self._save_all_data()

    def generate_full_report(self, current_time: datetime) -> str:
        """Génère le bilan complet de la session"""
        report_hours = {6: ("01h00", "06h00"), 12: ("09h00", "12h00"), 
                       18: ("15h00", "18h00"), 0: ("21h00", "00h00")}
        start, end = report_hours[current_time.hour]
        
        # Stats
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
        
        if channel_id:
            channel_id = int(channel_id)
        
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
    # EXTRACTION ET ANALYSE
    # =================================================================

    # FONCTION CRITIQUE: Extrait le contenu de TOUTES les parenthèses
    def _extract_parentheses_content(self, text: str) -> List[str]:
        """Extrait le contenu de toutes les sections de parenthèses"""
        pattern = r'\(([^)]+)\)'
        return re.findall(pattern, text)

    def extract_game_number(self, message: str) -> Optional[int]:
        """Extrait le numéro de jeu"""
        patterns = [r'#N(\d+)\.', r'🔵(\d+)🔵', r'Jeu\s*(\d+)', r'J\s*(\d+)']
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None

    def extract_game_number_from_text(self, text: str) -> Optional[int]:
        """Extrait le numéro de jeu avec robustesse"""
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

    # FONCTION CRITIQUE CORRIGÉE: Assure un formatage STRICT et robuste
    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        """Extrait les détails des cartes avec formatage STRICT
        GARANTIT le format: '9❤️' sans espace, avec le bon emoji complet"""
        
        # Étape 1: Normaliser tous les formats d'emojis possibles
        normalized = content.replace("♥", "❤️").replace("♥️", "❤️")
        normalized = normalized.replace("♠", "♠️").replace("♠️", "♠️")
        normalized = normalized.replace("♦", "♦️").replace("♦️", "♦️")
        normalized = normalized.replace("♣", "♣️").replace("♣️", "♣️")
        
        # Étape 2: Supprimer les espaces qui séparent valeur et enseigne
        normalized = normalized.replace(" ", "")
        
        # Étape 3: Pattern robuste pour capturer toute carte
        # \d+ = chiffres (10, 9, etc.) | [AKQJ] = valeurs lettres
        # (❤️|♠️|♦️|♣️) = enseigne obligatoire
        pattern = r'(\d+|[AKQJ])(❤️|♠️|♦️|♣️)'
        matches = re.findall(pattern, normalized, re.IGNORECASE)
        
        # Étape 4: Retourner avec formatage STRICT
        formatted = []
        for value, suit in matches:
            formatted.append((value.upper(), suit))
        
        logger.debug(f"🃏 Cartes extraites: {formatted}")
        return formatted

    # FONCTION CRITIQUE CORRIGÉE: Retourne le format EXACT pour le matching
    def get_all_cards_in_first_group(self, message: str) -> List[str]:
        """Retourne TOUTES les cartes du PREMIER groupe avec format STRICT
        EXEMPLE: '(K♣️9❤️)' → ['K♣️', '9❤️']"""
        
        match = re.search(r'\(([^)]*)\)', message)
        if not match:
            logger.debug("❌ Aucun groupe de parenthèses trouvé")
            return []
        
        details = self.extract_card_details(match.group(1))
        cards = []
        for v, c in details:
            # FORCER le format exact: valeur + emoji (ex: '9❤️')
            card = f"{v.upper()}{c}"
            cards.append(card)
        
        logger.info(f"📌 PREMIER GROUPE: {cards}")
        return cards

    # FONCTION CRITIQUE CORRIGÉE: Retourne la PREMIÈRE carte au format STRICT
    def get_first_card_info(self, message: str) -> Optional[Tuple[str, str]]:
        """Retourne la PREMIÈRE carte du PREMIER groupe"""
        all_cards = self.get_all_cards_in_first_group(message)
        if all_cards:
            return all_cards[0], all_cards[0][-2:]  # '9❤️', '❤️'
        return None

    # =================================================================
    # COLLECTE DES DONNÉES
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
        
        # Nettoyage
        limit = game_number - 50
        self.sequential_history = {k: v for k, v in self.sequential_history.items() if k >= limit}
        self.collected_games = {g for g in self.collected_games if g >= limit}
        
        self._save_all_data()

    # =================================================================
    # ANALYSE ET CRÉATION DES 16 RÈGLES
    # =================================================================

    def analyze_and_set_smart_rules(self, chat_id: Optional[int] = None,
                                   initial_load: bool = False,
                                   force_activate: bool = False):
        """Analyse les données et crée EXACTEMENT 16 règles dynamiques"""
        
        logger.info("🔍 DÉBUT ANALYSE - Création des 16 règles dynamiques...")
        
        # 1. Groupement par enseigne de résultat
        result_suit_groups = defaultdict(lambda: defaultdict(int))
        
        for entry in self.inter_data:
            trigger_card = entry['declencheur']
            result_suit = entry['result_suit']
            result_normalized = result_suit.replace("♥️", "❤️")
            
            result_suit_groups[result_normalized][trigger_card] += 1
        
        # 2. Créer toutes les règles (TOP illimité)
        all_rules = []
        for result_suit in ['♠️', '❤️', '♦️', '♣️']:
            triggers = result_suit_groups.get(result_suit, {})
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
        
        self.last_inter_update_time = time.time()
        self._save_all_data()
        
        logger.info(f"✅ ANALYSE TERMINÉE: {len(self.smart_rules)} règles actives")
        
        # Notification
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

    def check_and_update_rules(self):
        """Mise à jour périodique (30 minutes)"""
        if time.time() - self.last_analysis_time > 1800:
            logger.info("🔄 Mise à jour INTER périodique (30 min)")
            if len(self.inter_data) >= 3:
                self.analyze_and_set_smart_rules(force_activate=True)

    def _send_inter_status(self, chat_id: int):
        """Envoie le statut détaillé du mode INTER"""
        if not self.telegram_message_sender:
            return
        
        msg, kb = self.get_inter_status()
        self.telegram_message_sender(chat_id, msg, reply_markup=kb)

    # =================================================================
    # VÉRIFICATION DES PRÉDICTIONS (CRITIQUE)
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
        DÉTERMINE SI ON DOIT PRÉDIRE
        CORRIGÉ: Vérifie CHAQUE règle contre CHAQUE carte du 1er groupe
        POSITION N'A AUCUNE IMPORTANCE
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
        
        # Vérifier écart STRICT de 3
        if self.last_predicted_game_number and (game_number - self.last_predicted_game_number < 3):
            logger.debug(f"⏳ Écart insuffisant: {game_number - self.last_predicted_game_number} < 3")
            return False, None, None, None
        
        # EXTRACTION PRIORITAIRE des parenthèses
        parent_content = self._extract_parentheses_content(message)
        if parent_content and len(parent_content) > 0:
            first_group = parent_content[0]
            logger.info(f"📌 CONTENU PARENTHÈSES: {first_group}")
            
            # VOIR TOUTES LES CARTES DU PREMIER GROUPE (format STRICT)
            all_cards = self.get_all_cards_in_first_group(message)
            logger.info(f"🃏 CARTES DU 1ER GROUPE: {all_cards}")
            
            # VOIR LES RÈGLES DISPONIBLES (format STRICT)
            active_rules = self.smart_rules if self.smart_rules else []
            logger.info(f"🎯 RÈGLES INTER ACTIVES: {[r['trigger'] for r in active_rules]}")
            
            # ========== LOGIQUE CRITIQUE CORRIGÉE ==========
            # Chercher si UNE SEULE des cartes du 1er groupe MATCH UNE règle
            if self.is_inter_mode_active and self.smart_rules:
                for rule in self.smart_rules:
                    # VÉRIFICATION: la règle (ex: "9❤️") est-elle DANS les cartes ?
                    logger.debug(f"🔍 VÉRIFIE: Règle '{rule['trigger']}' dans {all_cards}")
                    
                    if rule['trigger'] in all_cards:
                        predicted_suit = rule['predict']
                        self._last_trigger_used = rule['trigger']
                        self._last_rule_index = rule.get('rank', 1) - 1
                        logger.info(f"✅ MATCH TROUVÉ: {rule['trigger']} → {predicted_suit}")
                        return True, game_number, predicted_suit, True
                
                # Si on arrive ici, AUCUNE règle ne match
                logger.error("❌ AUCUNE RÈGLE NE MATCH AVEC LES CARTES DU 1ER GROUPE")
                logger.error(f"Cartes du 1er groupe: {all_cards}")
                logger.error(f"Règles disponibles: {[r['trigger'] for r in self.smart_rules]}")
            
            # Chercher dans les règles statiques
            if not self.is_inter_mode_active:
                cards = self.get_all_cards_in_first_group(message)
                for card in cards:
                    if card in STATIC_RULES:
                        predicted_suit = STATIC_RULES[card]
                        self._last_trigger_used = card
                        return True, game_number, predicted_suit, False
        
        logger.warning("❌ AUCUN CONTENU PARENTHÈSES VALIDE TROUVÉ")
        return False, None, None, None

    def prepare_prediction_text(self, game_number_source: int, predicted_costume: str) -> str:
        """Prépare le texte de prédiction (CORRIGÉ - f-string terminé)"""
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
