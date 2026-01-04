# handlers.py - VERSION ULTRA ROBUSTE & PROTÉGÉE
import logging
import json
import time
import re
from collections import defaultdict, deque
from typing import Dict, Any, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Import avec gestion d'erreur robuste
try:
    from card_predictor import CardPredictor, normalize_card
except ImportError as e:
    logger.error(f"❌ IMPOSSIBLE D'IMPORTER CARDPREDICTOR: {e}")
    CardPredictor = None
except Exception as e:
    logger.error(f"❌ ERREUR CRITIQUE lors de l'import: {e}")
    CardPredictor = None

PREDICTION_CHANNEL_ID = -1003554569009

# Trackers globaux
last_suit_predictions = deque(maxlen=3)
last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}

WELCOME_MESSAGE = """
👋 **BOT DE PRÉDICTION - MODE ULTRA ROBUSTE**

✅ Fonctions:
• 16 règles dynamiques (4 TOP par costume)
• Écart STRICT de 3 numéros
• Anti-répétition costume (max 2x)
• Rotation automatique (10 min)
• Quarantaine intelligente (1h)
• Protection contre les erreurs de type

📋 Commandes:
• `/start` - Message de bienvenue
• `/stat` - Statut complet
• `/debug` - Diagnostic complet
• `/inter activate` - Activer les 16 règles
• `/collect` - Voir données collectées
• `/qua` - Voir état des TOP 4

🎯 Mode: INTER (16 règles uniquement)
"""

class TelegramHandlers:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # ✅ Vérification que CardPredictor est bien chargé
        if CardPredictor is None:
            logger.error("❌ CardPredictor n'est pas disponible. Impossible de continuer.")
            self.card_predictor = None
            return
        
        try:
            self.card_predictor = CardPredictor(
                telegram_message_sender=self.send_message
            )
            
            self.card_predictor.last_rule_index_by_suit = last_rule_index_by_suit
            self.card_predictor.last_suit_predictions = last_suit_predictions
            
            logger.info("✅ TelegramHandlers initialisé - MODE ULTRA ROBUSTE")
        except Exception as e:
            logger.error(f"❌ Erreur initialisation CardPredictor: {e}")
            self.card_predictor = None

    # --- MESSAGERIE SÉCURISÉE ---
    def send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown',
                     message_id: Optional[int] = None, edit: bool = False,
                     reply_markup: Optional[Dict] = None) -> Optional[int]:
        if not chat_id or not text:
            logger.warning("🚫 Envoi annulé: chat_id ou texte vide")
            return None
        
        method = 'editMessageText' if (message_id or edit) else 'sendMessage'
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
        
        if message_id:
            payload['message_id'] = message_id
        
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
        
        try:
            logger.info(f"📤 ENVOI MESSAGE: chat_id={chat_id}, method={method}")
            response = requests.post(f"{self.base_url}/{method}", json=payload, timeout=15)
            
            if response.status_code == 200:
                result = response.json().get('result', {})
                logger.info(f"✅ Message envoyé: {result.get('message_id')}")
                return result.get('message_id')
            else:
                logger.error(f"❌ Erreur Telegram {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            logger.error("⏱️ Timeout envoi message Telegram")
        except Exception as e:
            logger.error(f"❌ Exception envoi: {e}")
        
        return None

    # --- COMMANDES ---
    def _handle_command_debug(self, chat_id: int):
        """Diagnostic complet avec vérification des types"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        cp = self.card_predictor
        
        # Vérification des types CRITIQUE
        preds_type = type(cp.predictions).__name__
        inter_type = type(cp.inter_data).__name__
        rules_type = type(cp.smart_rules).__name__
        quarantined_type = type(cp.quarantined_rules).__name__
        
        # Vérifier si on est dans une session
        in_session = cp.is_in_session()
        current_hour = cp.now().hour
        
        # Vérifier les prédictions en attente
        pending = [p for p in cp.predictions.values() if p.get('status') == 'pending'] if isinstance(cp.predictions, dict) else []
        
        # Vérifier dernier écart
        last_game = cp.last_predicted_game_number
        gap_ok = "Aucune" if last_game == 0 else f"J{last_game} (prochain: J{last_game + 3}+)"
        
        # Compter les règles par costume
        rules_by_suit = defaultdict(list)
        if isinstance(cp.smart_rules, list):
            for rule in cp.smart_rules:
                if isinstance(rule, dict) and 'predict' in rule:
                    rules_by_suit[rule['predict']].append(rule)
        
        debug_msg = (
            f"🔍 **DIAGNOSTIQUE COMPLET - VÉRIFICATION DES TYPES**\n\n"
            f"🛡️ **Types des données:**\n"
            f"  • predictions: {preds_type} ({len(cp.predictions) if isinstance(cp.predictions, dict) else 'ERREUR'})\n"
            f"  • inter_data: {inter_type} ({len(cp.inter_data) if isinstance(cp.inter_data, list) else 'ERREUR'})\n"
            f"  • smart_rules: {rules_type} ({len(cp.smart_rules) if isinstance(cp.smart_rules, list) else 'ERREUR'})\n"
            f"  • quarantined_rules: {quarantined_type}\n\n"
            f"⏰ Heure: {cp.now().strftime('%H:%M:%S')} (Session: {'✅' if in_session else '❌'})\n"
            f"🧠 Mode INTER: {'✅ ACTIF' if cp.is_inter_mode_active else '❌ INACTIF'}\n"
            f"⏳ En attente: {len(pending)}\n"
            f"🎯 Dernier gap: {gap_ok}\n"
            f"🔄 Derniers costumes: {list(cp.last_suit_predictions)}\n\n"
            f"📥 Canal Source: `{cp.target_channel_id}`\n"
            f"📤 Canal Pred: `{cp.prediction_channel_id}`\n"
            f"🔧 Token présent: {'✅' if self.bot_token else '❌'}\n\n"
            f"📋 RÈGLES PAR COSTUME:\n"
        )
        
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            suit_rules = sorted(rules_by_suit.get(suit, []), key=lambda x: x.get('count', 0), reverse=True)
            debug_msg += f"\n**{suit}** ({len(suit_rules)} règles):\n"
            for idx, rule in enumerate(suit_rules[:4], 1):
                debug_msg += f"  TOP{idx}: {rule.get('trigger', '?')} → {rule.get('predict', '?')} ({rule.get('count', 0)}x)\n"
        
        debug_msg += (
            f"\n💡 **Si problème de type:**\n"
            f"1. Exécutez `/reset` pour nettoyer\n"
            f"2. Vérifiez permissions fichiers\n"
            f"3. Redémarrez le bot proprement"
        )
        
        self.send_message(chat_id, debug_msg)
        logger.info("📊 Diagnostic envoyé")

    def _handle_command_stat(self, chat_id: int):
        """Statut amélioré avec vérification des types"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        cp = self.card_predictor
        
        # Vérification que predictions est bien un dict
        if not isinstance(cp.predictions, dict):
            logger.error(f"❌ CORRUPTION: predictions est {type(cp.predictions).__name__} au lieu de dict")
            self.send_message(chat_id, "❌ ERREUR: Données corrompues. Utilisez `/reset`")
            return
        
        pending = [p for p in cp.predictions.values() if p.get('status') == 'pending']
        last_gap = "Aucune" if cp.last_predicted_game_number == 0 else \
                   f"J{cp.last_predicted_game_number} (prochain: J{cp.last_predicted_game_number + 3}+)"
        
        msg = (
            f"📊 **STATUS DU BOT**\n\n"
            f"🧠 Mode: {'IA (16 TOP)' if cp.is_inter_mode_active else 'Statique'}\n"
            f"📥 Source: `{cp.target_channel_id}`\n"
            f"📤 Prediction: `{cp.prediction_channel_id}`\n"
            f"🧠 Règles actives: {len(cp.smart_rules)}/16\n"
            f"📈 Jeux collectés: {len(cp.inter_data)}\n"
            f"⏳ En attente: {len(pending)}\n"
            f"🎯 Dernier gap: {last_gap}\n"
            f"🔄 Derniers costumes: {list(cp.last_suit_predictions)}\n"
            f"⏰ Session: {'✅' if cp.is_in_session() else '❌'} {cp.current_session_label()}"
        )
        
        self.send_message(chat_id, msg)

    def _handle_command_inter(self, chat_id: int, text: str):
        """Gestion des commandes /inter avec vérification des données"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        # Vérification que inter_data est bien une liste
        if not isinstance(self.card_predictor.inter_data, list):
            logger.error("❌ CORRUPTION: inter_data n'est pas une liste")
            self.send_message(chat_id, "❌ ERREUR: Données corrompues. Utilisez `/reset`")
            return
        
        parts = text.lower().split()
        action = parts[1] if len(parts) > 1 else 'status'
        
        if action == 'activate':
            if len(self.card_predictor.inter_data) < 3:
                self.send_message(chat_id, f"⚠️ Pas assez de données: {len(self.card_predictor.inter_data)} jeux (min 3)")
                return
            
            self.card_predictor.analyze_and_set_smart_rules(chat_id=chat_id, force_activate=True)
            self.send_message(chat_id, "✅ **MODE INTER ACTIVÉ**\nAnalyse des 16 TOP en cours...")
            logger.info("🚀 MODE INTER ACTIVÉ MANUELLEMENT")
        
        elif action == 'default':
            self.card_predictor.is_inter_mode_active = False
            self.card_predictor._save_all_data()
            self.send_message(chat_id, "❌ **MODE INTER DÉSACTIVÉ**")
            logger.info("🛑 MODE INTER DÉSACTIVÉ")
            
        elif action == 'status':
            msg, kb = self.card_predictor.get_inter_status()
            self.send_message(chat_id, msg, reply_markup=kb)
        
        else:
            help_msg = """
🤖 **AIDE /INTER**
• `/inter status` - Voir statut
• `/inter activate` - ACTIVER (nécessite 3+ jeux)
• `/inter default` - Désactiver
"""
            self.send_message(chat_id, help_msg)
    
    def _handle_command_collect(self, chat_id: int):
        """Affiche l'état de la collecte avec vérification des types"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        # Vérification que les données sont du bon type
        if not isinstance(self.card_predictor.inter_data, list):
            logger.error("❌ CORRUPTION: inter_data n'est pas une liste")
            self.send_message(chat_id, "❌ ERREUR: Données corrompues. Utilisez `/reset`")
            return
        
        msg = self.card_predictor.get_collect_info()
        self.send_message(chat_id, msg)
        
        # Si moins de 3 jeux, expliquer
        if len(self.card_predictor.inter_data) < 3:
            self.send_message(chat_id, "⚠️ **Minimum 3 jeux nécessaires pour activer INTER**")
        else:
            self.send_message(chat_id, "✅ **OK pour activation INTER**")
    
    def _handle_command_qua(self, chat_id: int):
        """Affichage amélioré des règles avec vérification des types"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        # Vérification que smart_rules est bien une liste
        if not isinstance(self.card_predictor.smart_rules, list):
            logger.error("❌ CORRUPTION: smart_rules n'est pas une liste")
            self.send_message(chat_id, "❌ ERREUR: Données corrompues. Utilisez `/reset`")
            return
        
        try:
            cp = self.card_predictor
            cp.smart_rules = cp._get_active_rules()
            
            message = "🔒 **ÉTAT DES 16 RÈGLES - TOP 4**\n\n"
            
            total_quarantined = sum(len(q) for q in cp.quarantined_rules.values())
            active_count = len(cp.smart_rules)
            
            message += f"📊 Actives: {active_count}/16\n"
            message += f"🔒 Quarantaine: {total_quarantined}\n"
            message += f"📈 Données: {len(cp.inter_data)} jeux\n\n"
            
            for suit in ['♠️', '❤️', '♦️', '♣️']:
                message += f"━━━━━━━━━━━━━━━━━\n**{suit}:**\n━━━━━━━━━━━━━━━━━\n"
                
                suit_rules = [r for r in cp.smart_rules if r.get('predict') == suit]
                suit_rules = sorted(suit_rules, key=lambda x: x.get('count', 0), reverse=True)
                
                if suit_rules:
                    for idx, rule in enumerate(suit_rules[:4], 1):
                        trigger = rule.get('trigger', '?')
                        count = rule.get('count', 0)
                        message += f"  ✅ TOP{idx}: {trigger} ({count}x)\n"
                else:
                    message += f"  ⚠️ Aucune règle active\n"
                
                quarantined = cp.quarantined_rules.get(suit, {})
                if quarantined:
                    message += f"\n  🔒 Quarantaine: {len(quarantined)} règle(s)\n"
                    for trigger, used_count in list(quarantined.items())[:3]:
                        message += f"     → {trigger} ({used_count}x)\n"
                
                message += "\n"
            
            self.send_message(chat_id, message)
            
        except Exception as e:
            logger.error(f"❌ Erreur /qua: {e}")
    
    def _handle_command_bilan(self, chat_id: int):
        """Aperçu du bilan"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        try:
            msg = self.card_predictor.get_session_report_preview()
            self.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"❌ Erreur bilan: {e}")
    
    def _handle_command_reset(self, chat_id: int):
        """Réinitialisation avec gestion d'erreur"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        try:
            cp = self.card_predictor
            
            # Sauvegarder IDs
            saved_target = cp.target_channel_id
            saved_pred = cp.prediction_channel_id
            
            # Compter
            pred_count = len(cp.predictions) if isinstance(cp.predictions, dict) else 0
            inter_count = len(cp.inter_data) if isinstance(cp.inter_data, list) else 0
            rules_count = len(cp.smart_rules) if isinstance(cp.smart_rules, list) else 0
            qua_count = sum(len(q) for q in cp.quarantined_rules.values()) if isinstance(cp.quarantined_rules, dict) else 0
            
            # Reset trackers globaux
            global last_suit_predictions, last_rule_index_by_suit
            last_suit_predictions.clear()
            last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}
            
            # Reset complet
            cp.reset_all()
            
            # Restaurer IDs
            cp.target_channel_id = saved_target
            cp.prediction_channel_id = saved_pred
            
            message = (
                f"✅ **RÉINITIALISATION TERMINÉE**\n\n"
                f"📋 **DONNÉES SUPPRIMÉES:**\n"
                f"  • {pred_count} prédictions\n"
                f"  • {inter_count} jeux collectés\n"
                f"  • {rules_count} règles TOP 4\n"
                f"  • {qua_count} quarantaine\n\n"
                f"✅ **DONNÉES CONSERVÉES:**\n"
                f"  • Canal Source: `{saved_target}`\n"
                f"  • Canal Prédiction: `{saved_pred}`\n\n"
                f"🧠 Mode INTER: DÉSACTIVÉ\n"
                f"🎯 Bot prêt"
            )
            
            self.send_message(chat_id, message)
            logger.info("🔄 Reset complet effectué")
            
        except Exception as e:
            logger.error(f"❌ Erreur /reset: {e}")
    
    def _handle_callback_query(self, update_obj: Dict[str, Any]):
        """Gestion des callbacks des boutons inline avec vérification"""
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

    # --- GESTION MESSAGES ---
    def _process_source_channel_message(self, message: Dict[str, Any]):
        """TRAITEMENT PRINCIPAL DU CANAL SOURCE"""
        try:
            text = message.get('text', '')
            chat_id = message['chat']['id']
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📥 MESSAGE CANAL SOURCE REÇU: {text[:100]}")
            logger.info(f"{'='*60}")
            
            # 1. VÉRIFICATION PRÉDICTIONS EN ATTENTE
            logger.info("🔍 VÉRIFICATION PRÉDICTIONS EN ATTENTE")
            self._verify_pending_predictions(text, is_edit=False)
            
            # 2. COLLECTE DES DONNÉES
            game_num = self.card_predictor.extract_game_number_from_text(text)
            if game_num:
                logger.info(f"📊 COLLECTE JEU: {game_num}")
                self.card_predictor.collect_inter_data(game_num, text)
            
            # 3. MISE À JOUR DES RÈGLES (toutes les 10 minutes)
            self.card_predictor.check_and_update_rules()
            
            # 4. PRÉDICTION AUTOMATIQUE
            logger.info("🤖 TENTATIVE PRÉDICTION AUTOMATIQUE")
            self._check_manual_prediction(text)
            
            logger.info("✅ TRAITEMENT TERMINÉ")
            
        except Exception as e:
            logger.error(f"❌ ERREUR CRITIQUE traitement canal source: {e}", exc_info=True)

    def _check_manual_prediction(self, text: str):
        """Vérifie et envoie une prédiction avec vérification des types"""
        try:
            logger.info("🔍 VÉRIFICATION PRÉDICTION MANUELLE")
            
            ok, game_num, suit, is_inter = self.card_predictor.should_predict(text)
            
            if ok and game_num and suit:
                logger.info(f"✅ CONDITIONS VALIDÉES: J{game_num} → {suit}")
                
                # Vérifier les conditions supplémentaires
                can_predict, reason = self._can_make_prediction(game_num, suit)
                
                if can_predict:
                    logger.info(f"🚀 ENVOI PRÉDICTION: J{game_num} → {suit}")
                    
                    txt = self.card_predictor.prepare_prediction_text(game_num, suit)
                    mid = self.send_message(PREDICTION_CHANNEL_ID, txt)
                    
                    if mid:
                        trigger = self.card_predictor._last_trigger_used or '?'
                        rule_idx = self.card_predictor._last_rule_index
                        
                        self.card_predictor.make_prediction(
                            game_num, suit, mid, is_inter=is_inter,
                            trigger_used=trigger, rule_index=rule_idx
                        )
                        
                        logger.info(f"✅ PRÉDICTION ENVOYÉE: J{game_num} → {suit} (ID: {mid})")
                    else:
                        logger.error("❌ ERREUR ENVOI MESSAGE PRÉDICTION")
                else:
                    logger.warning(f"🚫 PRÉDICTION BLOQUÉE: {reason}")
            else:
                logger.warning("🚫 CONDITIONS NON RÉUNIES POUR PRÉDIRE")
        
        except Exception as e:
            logger.error(f"❌ ERREUR check_manual_prediction: {e}", exc_info=True)

    def _can_make_prediction(self, game_num: int, suit: str) -> tuple[bool, str]:
        """Vérifie toutes les conditions avant de prédire avec vérification des types"""
        if not self.card_predictor:
            return False, "Moteur non chargé"
        
        # Vérification que predictions est bien un dict
        if not isinstance(self.card_predictor.predictions, dict):
            logger.error("❌ CORRUPTION: predictions n'est pas un dict")
            return False, "Données corrompues"
        
        # Vérifier écart de 3 (déjà vérifié dans should_predict, mais double sécurité)
        if not self.card_predictor._check_gap_rule(game_num):
            return False, f"Écart de 3 non respecté (dernier: {self.card_predictor.last_predicted_game_number})"
        
        # Vérifier anti-répétition
        if not self.card_predictor._check_suit_repetition(suit):
            return False, f"Costume {suit} déjà prédict 2x d'affilée"
        
        logger.info(f"✅ TOUTES CONDITIONS VALIDÉES pour J{game_num} → {suit}")
        return True, "✅ Toutes conditions validées"

    def handle_update(self, update: Dict[str, Any]):
        """Point d'entrée principal avec gestion d'erreur robuste"""
        if not self.card_predictor:
            logger.error("🚫 CardPredictor non disponible")
            return
        
        try:
            # Vérification bilans (heures exactes)
            self.card_predictor.check_and_send_scheduled_reports()
            
            # Traiter message selon son type
            if 'message' in update:
                self._process_message(update['message'])
            elif 'channel_post' in update:
                self._process_message(update['channel_post'])
            elif 'edited_message' in update:
                self._process_edited_message(update['edited_message'])
            elif 'edited_channel_post' in update:
                self._process_edited_message(update['edited_channel_post'])
            elif 'callback_query' in update:
                self._handle_callback_query(update['callback_query'])
            
        except Exception as e:
            logger.error(f"❌ ERREUR CRITIQUE handle_update: {e}", exc_info=True)

    def _process_message(self, message: Dict[str, Any]):
        """Traite un message avec vérification des types"""
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '')
            
            # Commandes
            if text.startswith('/debug'):
                self._handle_command_debug(chat_id)
                return
            elif text.startswith('/inter'):
                self._handle_command_inter(chat_id, text)
                return
            elif text.startswith('/stat'):
                self._handle_stat_command(chat_id)
                return
            elif text.startswith('/collect'):
                self._handle_command_collect(chat_id)
                return
            elif text.startswith('/qua'):
                self._handle_command_qua(chat_id)
                return
            elif text.startswith('/bilan'):
                self._handle_command_bilan(chat_id)
                return
            elif text.startswith('/start'):
                self.send_message(chat_id, WELCOME_MESSAGE)
                return
            elif text.startswith('/reset'):
                self._handle_command_reset(chat_id)
                return
            
            # Canal source
            if str(chat_id) == str(self.card_predictor.target_channel_id):
                logger.info(f"📍 MESSAGE DU CANAL SOURCE DÉTECTÉ")
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
                game_num = self.card_predictor.extract_game_number_from_text(text)
                if game_num:
                    self.card_predictor.collect_inter_data(game_num, text)
                
                # Vérifier les prédictions en attente
                self._verify_pending_predictions(text, is_edit=True)
        
        except Exception as e:
            logger.error(f"❌ Erreur traitement message édité: {e}")

    def _verify_pending_predictions(self, text: str, is_edit: bool = False):
        """Vérifie les prédictions en attente avec vérification des types"""
        try:
            current_game = self.card_predictor.extract_game_number_from_text(text)
            if not current_game:
                return
            
            logger.info(f"🔍 VÉRIFICATION JEU {current_game} (edit: {is_edit})")
            
            # Vérification que predictions est bien un dict
            if not isinstance(self.card_predictor.predictions, dict):
                logger.error("❌ CORRUPTION: predictions n'est pas un dict dans _verify_pending_predictions")
                return
            
            for pred_game_num, prediction in list(self.card_predictor.predictions.items()):
                if not isinstance(prediction, dict):
                    logger.error(f"❌ CORRUPTION: prediction {pred_game_num} n'est pas un dict")
                    continue
                
                if prediction.get('status') != 'pending':
                    continue
                
                for offset in [0, 1, 2]:
                    expected_game = int(pred_game_num) + offset
                    
                    if current_game == expected_game:
                        logger.info(f"🎯 VÉRIFICATION OFFSET {offset}: J{pred_game_num}+{offset}")
                        
                        res = self.card_predictor._verify_prediction_common(text)
                        
                        if res and res.get('type') == 'edit_message':
                            message_id = res.get('message_id_to_edit')
                            if message_id:
                                self.send_message(
                                    PREDICTION_CHANNEL_ID,
                                    res['new_message'],
                                    message_id=message_id,
                                    edit=True
                                )
                                logger.info(f"✅ PRÉDICTION VÉRIFIÉE: {res['predicted_game']}")
                                break
        
        except Exception as e:
            logger.error(f"❌ Erreur vérification: {e}")

# Dictionnaire de suivi des messages par utilisateur
user_message_counts = defaultdict(list)

__all__ = ['TelegramHandlers', 'PREDICTION_CHANNEL_ID', 'WELCOME_MESSAGE']
