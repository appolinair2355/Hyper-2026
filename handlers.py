# handlers.py - VERSION COMPLET CORRIGÉE

import logging
import json
import time
import re
from collections import defaultdict, deque
from typing import Dict, Any, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Importation robuste
try:
    from card_predictor import CardPredictor
except ImportError:
    logger.error("❌ IMPOSSIBLE D'IMPORTER CARDPREDICTOR")
    CardPredictor = None

# =================================================================
# CONSTANTES GLOBALES ET TRACKERS
# =================================================================

# ID du canal de prédiction (crucial - ne pas modifier)
PREDICTION_CHANNEL_ID = -1003554569009

# Trackers globaux pour la rotation des règles
last_suit_predictions = deque(maxlen=3)
last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}

# Messages de bienvenue
WELCOME_MESSAGE = """
👋 **BIENVENUE SUR LE BOT ENSEIGNE !** ♠️♥️♦️♣️

✅ **NOUVELLES FONCTIONS:**
• Rotation automatique des 16 TOP (4 par costume)
• Anti-répétition de costume (max 2x)
• Analyse prioritaire du 1er contenu entre parenthèses
• Écart strict de 3 numéros
• Règles en quarantaine immédiate après utilisation
• Bilans automatiques aux heures exactes

━━━━━━━━━━━━━━━━━━━━━
📋 **COMMANDES DISPONIBLES**
━━━━━━━━━━━━━━━━━━━━━

**🔹 Informations**
• `/start` - Afficher ce message
• `/stat` - Voir l'état du bot
• `/qua` - Voir les TOP utilisés et quarantaine

**🔹 Mode Intelligent (16 RÈGLES)**
• `/inter status` - Voir les règles actives
• `/inter activate` - ACTIVER les 16 règles dynamiques
• `/inter default` - Désactiver INTER

**🔹 Données & Statistiques**
• `/collect` - Voir toutes les données collectées
• `/bilan` - Aperçu du prochain rapport
• `/reset` - ⚠️ RÉINITIALISER COMPLETEMENT

━━━━━━━━━━━━━━━━━━━━━
🧠 **MODE INTER :** 
• Utilisation UNIQUEMENT des 16 TOP
• Rotation round-robin automatique
• Remplacement immédiat quand règle utilisée
• MAJ toutes les 10 minutes
• Écart strict de 3 entre prédictions
━━━━━━━━━━━━━━━━━━━━━
"""

class TelegramHandlers:
    def __init__(self, bot_token: str):
        """Initialise le gestionnaire Telegram avec tous les trackers"""
        
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # Injection des trackers globaux
        global last_rule_index_by_suit, last_suit_predictions
        
        # ✅ NOUVEAU CODE (corrigé)
if CardPredictor:
    self.card_predictor = CardPredictor(
        telegram_message_sender=self.send_message
    )

            
            # Transférer les trackers globaux
            self.card_predictor.last_rule_index_by_suit = last_rule_index_by_suit
            self.card_predictor.last_suit_predictions = last_suit_predictions
            
            logger.info("✅ TelegramHandlers initialisé avec système 16 règles")
        else:
            self.card_predictor = None
            logger.error("❌ CardPredictor non disponible")

    # =================================================================
    # MESSAGERIE TÉLÉGRAM
    # =================================================================

    def _check_rate_limit(self, user_id: int) -> bool:
        """Vérifie la limite de messages par utilisateur (30/min)"""
        now = time.time()
        
        if user_id not in user_message_counts:
            user_message_counts[user_id] = []
        
        # Nettoyer les anciens timestamps
        user_message_counts[user_id] = [
            t for t in user_message_counts[user_id] 
            if now - t < 60
        ]
        
        user_message_counts[user_id].append(now)
        return len(user_message_counts[user_id]) <= 30

    def send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown',
                     message_id: Optional[int] = None, edit: bool = False,
                     reply_markup: Optional[Dict] = None) -> Optional[int]:
        """Envoie ou édite un message Telegram"""
        
        if not chat_id or not text:
            logger.warning("🚫 Envoi message annulé: chat_id ou texte vide")
            return None
        
        method = 'editMessageText' if (message_id or edit) else 'sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        if message_id:
            payload['message_id'] = message_id
        
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

        try:
            response = requests.post(
                f"{self.base_url}/{method}", 
                json=payload, 
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json().get('result', {})
                return result.get('message_id')
            else:
                logger.error(f"❌ Erreur Telegram {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            logger.error("⏱️ Timeout envoi message Telegram")
        except Exception as e:
            logger.error(f"❌ Exception envoi message: {e}")
        
        return None

    # =================================================================
    # COMMANDES UTILISATEUR
    # =================================================================

    def _handle_command_deploy(self, chat_id: int):
        """Envoie le package de déploiement"""
        try:
            zip_filename = 'pack.zip'
            
            if not os.path.exists(zip_filename):
                for fallback in ['yoi.zip', 'appo.zip']:
                    if os.path.exists(fallback):
                        zip_filename = fallback
                        break
                else:
                    self.send_message(chat_id, "❌ Fichier de déploiement (pack.zip) non trouvé!")
                    return

            self.send_message(chat_id, f"📦 **Envoi du package {zip_filename}...**")
            
            url = f"{self.base_url}/sendDocument"
            with open(zip_filename, 'rb') as f:
                files = {'document': (zip_filename, f, 'application/zip')}
                
                data_count = len(self.card_predictor.inter_data) if self.card_predictor else 0
                rules_count = len(self.card_predictor.smart_rules) if self.card_predictor else 0
                
                data = {
                    'chat_id': chat_id,
                    'caption': f'📦 **{zip_filename} - Package BOT**\n\n'
                              f'✅ Mode INTER: Rotation 16 règles\n'
                              f'✅ Écart: 3 (strict)\n'
                              f'✅ Anti-répétition: 2x\n'
                              f'✅ Canal Pred: {PREDICTION_CHANNEL_ID}\n'
                              f'📊 Données: {data_count} jeux\n'
                              f'🧠 Règles: {rules_count}/16 actives',
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=60)
            
            if response.json().get('ok'):
                logger.info(f"✅ {zip_filename} envoyé avec succès")
                self.send_message(chat_id, f"✅ **{zip_filename} envoyé!**")
            else:
                self.send_message(chat_id, f"❌ Erreur : {response.text}")
                    
        except Exception as e:
            logger.error(f"❌ Erreur /deploy : {e}")
            self.send_message(chat_id, f"❌ Erreur : {str(e)}")

    def _handle_command_collect(self, chat_id: int):
        """Affiche l'état de la collecte de données"""
        if not self.card_predictor: 
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        # Utiliser la méthode get_collect_info du card_predictor
        msg = self.card_predictor.get_collect_info()
        self.send_message(chat_id, msg)

    def _handle_command_bilan(self, chat_id: int):
        """Affiche un aperçu du bilan de fin de session"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        try:
            # Générer un aperçu du bilan
            msg = self.card_predictor.get_session_report_preview()
            self.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"❌ Erreur aperçu bilan: {e}")
            self.send_message(chat_id, "❌ Erreur lors du calcul du bilan.")

    def _handle_command_qua(self, chat_id: int):
        """Affiche l'état des 16 règles avec quarantaine et statistiques"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        try:
            cp = self.card_predictor
            
            # Forcer la mise à jour des règles actives
            cp.smart_rules = cp._get_active_rules()
            
            message = "🔒 **ÉTAT DES 16 RÈGLES - MODE INTER**\n\n"
            
            # Statistiques globales
            total_quarantined = sum(len(q) for q in cp.quarantined_rules.values())
            active_count = len(cp.smart_rules)
            
            message += f"📊 **Actives:** {active_count}/16\n"
            message += f"🔒 **Quarantaine:** {total_quarantined} règles\n"
            message += f"📈 **Données:** {len(cp.inter_data)} jeux analysés\n\n"
            
            # Détails par costume
            for suit in ['♠️', '❤️', '♦️', '♣️']:
                message += f"━━━━━━━━━━━━━━━━━\n**{suit}**:\n━━━━━━━━━━━━━━━━━\n"
                
                # Règles actives (TOP 4)
                suit_rules = [r for r in cp.smart_rules if r.get('predict') == suit]
                
                if suit_rules:
                    for idx, rule in enumerate(suit_rules, 1):
                        trigger = rule.get('trigger', '?')
                        count = rule.get('count', 0)
                        message += f"  ✅ **TOP{idx}:** {trigger} ({count}x)\n"
                else:
                    message += f"  ⚠️ Aucune règle active\n"
                
                # Règles en quarantaine
                quarantined = cp.quarantined_rules.get(suit, {})
                if quarantined:
                    message += f"\n  🔒 **Quarantaine:** {len(quarantined)} règle(s)\n"
                    for trigger, used_count in list(quarantined.items())[:3]:
                        message += f"     → {trigger} ({used_count}x utilisée)\n"
                
                message += "\n"
            
            # État de la rotation
            message += "🎯 **Prochaine rotation (Round-Robin):**\n"
            for suit in ['♠️', '❤️', '♦️', '♣️']:
                next_idx = cp.last_rule_index_by_suit.get(suit, 0) + 1
                message += f"  {suit}: TOP{next_idx}\n"
            
            # Derniers costumes prédits
            if cp.last_suit_predictions:
                message += f"\n📌 **Derniers costumes:** {list(cp.last_suit_predictions)}\n"
            
            self.send_message(chat_id, message)
            
        except Exception as e:
            logger.error(f"❌ Erreur /qua : {e}", exc_info=True)
            self.send_message(chat_id, f"❌ Erreur : {str(e)}")

    def _handle_command_reset(self, chat_id: int):
        """⚠️ RÉINITIALISATION COMPLET DU BOT"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        try:
            cp = self.card_predictor
            
            # Sauvegarder les IDs des canaux
            saved_target_id = cp.target_channel_id
            saved_pred_id = cp.prediction_channel_id
            
            # Compter avant suppression
            pred_count = len(cp.predictions)
            inter_count = len(cp.inter_data)
            rules_count = len(cp.smart_rules)
            qua_count = sum(len(q) for q in cp.quarantined_rules.values())
            
            # Réinitialiser les trackers globaux
            global last_suit_predictions, last_rule_index_by_suit
            last_suit_predictions.clear()
            last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
            
            # Appeler la méthode de reset du card_predictor
            cp.reset_all()
            
            # Message de confirmation détaillé
            message = (
                f"✅ **RÉINITIALISATION COMPLETÉE**\n\n"
                f"📋 **DONNÉES SUPPRIMÉES:**\n"
                f"  • {pred_count} prédictions\n"
                f"  • {inter_count} jeux collectés\n"
                f"  • {rules_count} règles TOP 4\n"
                f"  • {qua_count} règles en quarantaine\n\n"
                f"✅ **DONNÉES CONSERVÉES:**\n"
                f"  • Canal Source: `{saved_target_id or 'Non défini'}`\n"
                f"  • Canal Prédiction: `{saved_pred_id}`\n\n"
                f"🧠 Mode INTER: DÉSACTIVÉ\n"
                f"🔄 Trackers: RESET\n"
                f"🎯 Bot: VIERGE ET PRÊT ✅"
            )
            
            self.send_message(chat_id, message)
            logger.info("🔄 Reset complet effectué avec succès")
            
        except Exception as e:
            logger.error(f"❌ Erreur /reset : {e}", exc_info=True)
            self.send_message(chat_id, f"❌ Erreur lors de la réinitialisation: {str(e)}")

    def _handle_command_inter(self, chat_id: int, text: str):
        """Gestion des commandes /inter"""
        if not self.card_predictor: 
            self.send_message(chat_id, "❌ Le moteur de prédiction n'est pas chargé.")
            return
        
        parts = text.lower().split()
        action = parts[1] if len(parts) > 1 else 'status'
        
        if action == 'activate':
            # Forcer la création des 16 règles
            self.card_predictor.analyze_and_set_smart_rules(chat_id=chat_id, force_activate=True)
            self.send_message(chat_id, "✅ **MODE INTER ACTIVÉ**\nAnalyse des 16 TOP en cours...")
        
        elif action == 'default':
            # Désactiver le mode INTER
            self.card_predictor.is_inter_mode_active = False
            self.card_predictor._save_all_data()
            self.send_message(chat_id, "❌ **MODE INTER DÉSACTIVÉ**\nRetour aux règles statiques.")
            
        elif action == 'status':
            # Voir le statut détaillé
            msg, kb = self.card_predictor.get_inter_status()
            self.send_message(chat_id, msg, reply_markup=kb)
        
        else:
            # Aide sur /inter
            help_msg = """
🤖 **AIDE COMMANDE /INTER**

• `/inter status` - Voir les 16 règles actives
• `/inter activate` - ACTIVER le mode intelligent
• `/inter default` - Désactiver et retourner aux règles statiques
"""
            self.send_message(chat_id, help_msg)

    def _handle_callback_query(self, update_obj: Dict[str, Any]):
        """Gestion des callbacks des boutons inline"""
        try:
            data = update_obj.get('data', '')
            message = update_obj.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            msg_id = message.get('message_id')
            
            if not chat_id or not self.card_predictor:
                return
            
            # Actions INTER
            if data == 'inter_apply':
                self.card_predictor.analyze_and_set_smart_rules(chat_id=chat_id, force_activate=True)
                msg, kb = self.card_predictor.get_inter_status()
                self.send_message(chat_id, msg, message_id=msg_id, edit=True, reply_markup=kb)
            
            elif data == 'inter_default':
                self.card_predictor.is_inter_mode_active = False
                self.card_predictor._save_all_data()
                msg, kb = self.card_predictor.get_inter_status()
                self.send_message(chat_id, msg, message_id=msg_id, edit=True, reply_markup=kb)
                
            # Actions CONFIG
            elif data.startswith('config_'):
                if 'cancel' in data:
                    self.send_message(chat_id, "✅ Configuration annulée.", message_id=msg_id, edit=True)
                else:
                    type_c = 'source' if 'source' in data else 'prediction'
                    self.card_predictor.set_channel_id(chat_id, type_c)
                    self.send_message(chat_id, f"✅ Ce canal est maintenant défini comme **{type_c.upper()}**.", message_id=msg_id, edit=True)
        
        except Exception as e:
            logger.error(f"❌ Erreur callback_query: {e}")

    # =================================================================
    # FONCTIONS DE VÉRIFICATION PRÉDICTION
    # =================================================================

    def _extract_parentheses_content(self, text: str) -> Optional[str]:
        """
        Extraction PRIORITAIRE du 1er contenu entre parenthèses
        Ex: "Jeu 45 (A♣️) texte" → "A♣️"
        """
        if not text:
            return None
        
        match = re.search(r'\(([^)]+)\)', text)
        if match:
            content = match.group(1).strip().upper()
            # Normaliser les emojis de cartes
            content = content.replace('♥', '❤️').replace('♦', '♦️')
            content = content.replace('♠', '♠️').replace('♣', '♣️')
            # Nettoyer
            content = re.sub(r'[^\w\s♠️❤️♦️♣️]', '', content)
            return content
        return None

    def _can_make_prediction(self, game_num: int, suit: str) -> tuple[bool, str]:
        """
        Vérifie TOUTES les conditions avant de prédire
        Retour: (booléen, raison)
        """
        if not self.card_predictor:
            return False, "Moteur non chargé"
        
        # Vérifier écart de 3
        if not self.card_predictor._check_gap_rule(game_num):
            return False, f"Écart de 3 non respecté (dernier: {self.card_predictor.last_predicted_game_number})"
        
        # Vérifier anti-répétition costume
        if not self.card_predictor._check_suit_repetition(suit):
            return False, f"Costume {suit} déjà prédit trop de fois d'affilée"
        
        # Vérifier règle disponible
        rule, idx = self.card_predictor._get_next_available_rule(suit)
        if not rule:
            return False, f"Aucune règle disponible pour {suit} (toutes utilisées)"
        
        return True, "✅ Toutes conditions validées"

    # =================================================================
    # GESTION PRINCIPALE DES UPDATES (CRITIQUE)
    # =================================================================

    def handle_update(self, update: Dict[str, Any]):
        """Point d'entrée principal pour tous les événements Telegram"""
        
        if not self.card_predictor:
            logger.error("🚫 CardPredictor non disponible, update ignoré")
            return
        
        try:
            # 1. VÉRIFIER LES BILANS HORAIRES (priorité)
            self.card_predictor.check_and_send_scheduled_reports()
            
            # 2. TRAITER LES MESSAGES ENTRANTS
            message = None
            
            # Message normal
            if 'message' in update:
                message = update['message']
            elif 'channel_post' in update:
                message = update['channel_post']
            
            if message and 'text' in message:
                self._process_message(message)
            
            # 3. TRAITER LES MESSAGES ÉDITÉS
            elif 'edited_message' in update or 'edited_channel_post' in update:
                edited_msg = update.get('edited_message') or update.get('edited_channel_post')
                if edited_msg and 'text' in edited_msg:
                    self._process_edited_message(edited_msg)
            
            # 4. TRAITER LES CALLBACKS
            elif 'callback_query' in update:
                self._handle_callback_query(update['callback_query'])
            
            # 5. TRAITER L'AJOUT AU GROUPE
            elif 'my_chat_member' in update:
                self._handle_new_chat_member(update['my_chat_member'])
        
        except Exception as e:
            logger.error(f"❌ ERREUR CRITIQUE handle_update: {e}", exc_info=True)

    def _process_message(self, message: Dict[str, Any]):
        """Traite un message entrant (normal ou canal)"""
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '')
            user_id = message.get('from', {}).get('id', 0)
            
            if not self._check_rate_limit(user_id):
                return
            
            # --- COMMANDES ---
            if text.startswith('/inter'):
                self._handle_command_inter(chat_id, text)
                return
            
            elif text.startswith('/config'):
                self._handle_config_command(chat_id)
                return
            
            elif text.startswith('/start'):
                self.send_message(chat_id, WELCOME_MESSAGE)
                return
            
            elif text.startswith('/stat'):
                self._handle_stat_command(chat_id)
                return
            
            elif text.startswith('/deploy'):
                self._handle_command_deploy(chat_id)
                return
            
            elif text.startswith('/collect'):
                self._handle_command_collect(chat_id)
                return
            
            elif text.startswith('/qua'):
                self._handle_command_qua(chat_id)
                return
            
            elif text.startswith('/reset'):
                self._handle_command_reset(chat_id)
                return
            
            elif text.startswith('/bilan'):
                self._handle_command_bilan(chat_id)
                return
            
            # --- TRAITEMENT CANAL SOURCE ---
            if str(chat_id) == str(self.card_predictor.target_channel_id):
                self._process_source_channel_message(message)
        
        except Exception as e:
            logger.error(f"❌ Erreur traitement message: {e}", exc_info=True)

    def _process_edited_message(self, edited_msg: Dict[str, Any]):
        """Traite un message édité du canal source"""
        try:
            chat_id = edited_msg['chat']['id']
            text = edited_msg.get('text', '')
            
            if str(chat_id) == str(self.card_predictor.target_channel_id):
                # Collecter les données
                game_num = self.card_predictor.extract_game_number(text)
                if game_num:
                    self.card_predictor.collect_inter_data(game_num, text)
                
                # Vérifier les prédictions en attente
                self._verify_pending_predictions(text, is_edit=True)
        
        except Exception as e:
            logger.error(f"❌ Erreur traitement message édité: {e}")

    def _process_source_channel_message(self, message: Dict[str, Any]):
        """Traite un message du canal source (prediction + collecte)"""
        try:
            text = message.get('text', '')
            
            # A. 🧠 COLLECTE DES DONNÉES (toujours)
            game_num = self.card_predictor.extract_game_number(text)
            if game_num:
                # Extraction prioritaire des parenthèses
                parent_content = self._extract_parentheses_content(text)
                if parent_content:
                    logger.info(f"📌 Parenthèses détectées: {parent_content}")
                
                self.card_predictor.collect_inter_data(game_num, text)
                logger.debug(f"📊 Données collectées jeu {game_num}")
            
            # B. 🔍 VÉRIFICATION COMPLÈTE DE TOUTES LES PRÉDICTIONS EN ATTENTE
            self._verify_pending_predictions(text, is_edit=False)
            
            # C. 🤖 PRÉDICTION AUTOMATIQUE (mode INTER)
            self.card_predictor.check_and_send_automatic_predictions()
            
            # D. 👤 PRÉDICTION MANUELLE (si besoin)
            self._check_manual_prediction(text)
        
        except Exception as e:
            logger.error(f"❌ Erreur traitement canal source: {e}", exc_info=True)

    def _verify_pending_predictions(self, text: str, is_edit: bool = False):
        """Vérifie TOUS les offsets (0, 1, 2) pour les prédictions en attente"""
        try:
            current_game = self.card_predictor.extract_game_number_from_text(text)
            if not current_game:
                return
            
            action_type = "éditée" if is_edit else "auto"
            
            for pred_game_num, prediction in list(self.card_predictor.predictions.items()):
                if prediction.get('status') != 'pending':
                    continue
                
                # Vérifier tous les offsets
                for offset in [0, 1, 2]:
                    expected_game = int(pred_game_num) + offset
                    
                    if current_game == expected_game:
                        # Vérifier la prédiction
                        if is_edit:
                            res = self.card_predictor.verify_prediction_from_edit(text)
                        else:
                            res = self.card_predictor._verify_prediction_common(text)
                        
                        if res and res.get('type') == 'edit_message':
                            message_id_to_edit = res.get('message_id_to_edit')
                            if message_id_to_edit:
                                self.send_message(
                                    PREDICTION_CHANNEL_ID, 
                                    res['new_message'], 
                                    message_id=message_id_to_edit, 
                                    edit=True
                                )
                                
                                logger.info(
                                    f"✅ Vérification {action_type}: Jeu {pred_game_num} +{offset} → {res['result']}"
                                )
                                
                                # Ne pas vérifier d'autres offsets pour cette prédiction
                                break
        
        except Exception as e:
            logger.error(f"❌ Erreur vérification prédictions: {e}")

    def _check_manual_prediction(self, text: str):
        """Vérifie si une prédiction manuelle est nécessaire"""
        try:
            ok, game_num, suit, is_inter = self.card_predictor.should_predict(text)
            
            if ok and game_num and suit:
                # Vérifier toutes les conditions
                can_predict, reason = self._can_make_prediction(game_num, suit)
                
                if can_predict:
                    # Préparer et envoyer la prédiction
                    txt = self.card_predictor.prepare_prediction_text(game_num, suit)
                    mid = self.send_message(PREDICTION_CHANNEL_ID, txt)
                    
                    if mid:
                        trigger = self.card_predictor._last_trigger_used or '?'
                        rule_idx = self.card_predictor._last_rule_index
                        
                        # Enregistrer la prédiction
                        self.card_predictor.make_prediction(
                            game_num, suit, mid, is_inter=is_inter,
                            trigger_used=trigger, rule_index=rule_idx
                        )
                        
                        # Mettre à jour les trackers
                        global last_suit_predictions
                        last_suit_predictions.append(suit)
                        
                        logger.info(
                            f"👤 Prédiction manuelle: J{game_num} → {suit} (trigger: {trigger})"
                        )
                else:
                    logger.warning(f"🚫 Prédiction bloquée: {reason}")
        
        except Exception as e:
            logger.error(f"❌ Erreur check manual prediction: {e}")

    def _handle_config_command(self, chat_id: int):
        """Affiche le menu de configuration des canaux"""
        kb = {
            'inline_keyboard': [[
                {'text': '📥 Source', 'callback_data': 'config_source'},
                {'text': '📤 Prédiction', 'callback_data': 'config_prediction'},
                {'text': '❌ Annuler', 'callback_data': 'config_cancel'}
            ]]
        }
        self.send_message(chat_id, "⚙️ **CONFIGURATION DES CANAUX**\nQuel est le rôle de ce canal ?", reply_markup=kb)

    def _handle_stat_command(self, chat_id: int):
        """Affiche le statut du bot"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ Le moteur n'est pas chargé.")
            return
        
        cp = self.card_predictor
        
        sid = cp.target_channel_id or "Non défini"
        pid = cp.prediction_channel_id or PREDICTION_CHANNEL_ID
        mode = "IA (16 TOP)" if cp.is_inter_mode_active else "Statique"
        active_rules = len(cp.smart_rules)
        
        message = (
            f"📊 **STATUS DU BOT**\n\n"
            f"🎯 Mode: {mode}\n"
            f"📥 Canal Source: `{sid}`\n"
            f"📤 Canal Prédiction: `{pid}`\n"
            f"🧠 Règles actives: {active_rules}/16\n"
            f"📈 Jeux collectés: {len(cp.inter_data)}\n"
            f"⏳ Prédictions en attente: {sum(1 for p in cp.predictions.values() if p.get('status') == 'pending')}\n"
            f"🔄 Dernier costume: {list(last_suit_predictions)}"
        )
        
        self.send_message(chat_id, message)

    def _handle_new_chat_member(self, update: Dict[str, Any]):
        """Gère l'ajout du bot à un groupe/canal"""
        try:
            new_member = update.get('new_chat_member', {})
            if new_member.get('status') in ['member', 'administrator']:
                chat_id = update['chat']['id']
                
                self.send_message(
                    chat_id, 
                    "✨ Merci de m'avoir ajouté !\n"
                    "Veuillez utiliser `/config` pour définir mon rôle "
                    "(Source ou Prédiction)."
                )
                logger.info(f"✅ Bot ajouté au canal {chat_id}")
        
        except Exception as e:
            logger.error(f"❌ Erreur new_chat_member: {e}")

# =================================================================
# INITIALISATION
# =================================================================

# Dictionnaire de suivi des messages par utilisateur
user_message_counts = defaultdict(list)

__all__ = ['TelegramHandlers', 'PREDICTION_CHANNEL_ID', 'WELCOME_MESSAGE']
