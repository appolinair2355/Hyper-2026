import logging
import json
import time
import re
from collections import defaultdict, deque
from typing import Dict, Any, Optional, List
import requests

logger = logging.getLogger(__name__)

# Import avec triple vérification
CardPredictor = None
import_error = None

try:
    from card_predictor import CardPredictor, normalize_card
    logger.info("✅ CardPredictor importé avec succès")
except ImportError as e:
    import_error = str(e)
    logger.critical(f"❌ IMPORT IMPOSSIBLE: {e}")
except Exception as e:
    import_error = str(e)
    logger.critical(f"❌ ERREUR CRITIQUE IMPORT: {e}")

PREDICTION_CHANNEL_ID = -1003554569009

# Trackers globaux (état partagé)
last_suit_predictions = deque(maxlen=3)
last_rule_index_by_suit = {'♠️': 0, '❤️': 0, '♦️': 0, '♣️': 0}

WELCOME_MESSAGE = """
👋 **BOT DE PRÉDICTION - PRODUCTION MODE**

✅ Fonctions:
• 16 règles dynamiques (4 TOP/costume)
• Écart 3+ numéros
• Anti-répétition costume
• Rotation automatique
• Quarantaine intelligente

📋 Commandes:
/start /stat /debug /inter /collect /qua /reset
"""

class TelegramHandlers:
    def __init__(self, bot_token: str):
        # ✅ VALIDATION EXPLICITE
        if not bot_token:
            raise ValueError("bot_token ne peut pas être vide ou None")
        
        if not isinstance(bot_token, str):
            raise TypeError(f"bot_token doit être str, reçu {type(bot_token)}")
        
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # ✅ VÉRIFICATION CRITIQUE DU MODULE
        if CardPredictor is None:
            logger.critical(f"❌ CardPredictor non disponible: {import_error}")
            raise RuntimeError(f"Impossible de charger CardPredictor: {import_error}")
        
        try:
            self.card_predictor = CardPredictor(
                telegram_message_sender=self.send_message
            )
            
            # Synchronisation des trackers
            self.card_predictor.last_rule_index_by_suit = last_rule_index_by_suit
            self.card_predictor.last_suit_predictions = last_suit_predictions
            
            logger.info("✅ TelegramHandlers initialisé avec succès")
            
        except Exception as e:
            logger.critical(f"❌ Échec init CardPredictor: {e}", exc_info=True)
            raise

    def send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown',
                     message_id: Optional[int] = None, edit: bool = False,
                     reply_markup: Optional[Dict] = None) -> Optional[int]:
        """Envoie un message Telegram avec retry automatique"""
        if not chat_id or not text:
            logger.warning("🚫 Envoi annulé: paramètres invalides")
            return None
        
        # ✅ VÉRIFICATION QUE L'URL EST BIEN DÉFINIE
        if not hasattr(self, 'base_url') or not self.base_url:
            logger.error("❌ base_url non définie")
            return None
        
        method = 'editMessageText' if (message_id or edit) else 'sendMessage'
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
        
        if message_id:
            payload['message_id'] = message_id
        
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        
        # ✅ RETRY LOGIC
        for attempt in range(3):
            try:
                logger.info(f"📤 ENVOI [{attempt+1}/3]: chat_id={chat_id}, method={method}")
                response = requests.post(
                    f"{self.base_url}/{method}", 
                    json=payload, 
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json().get('result', {})
                    msg_id = result.get('message_id')
                    logger.info(f"✅ Message envoyé: {msg_id}")
                    return msg_id
                else:
                    logger.error(f"❌ Erreur Telegram {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                logger.error(f"⏱️ Timeout (attempt {attempt+1})")
            except Exception as e:
                logger.error(f"❌ Exception (attempt {attempt+1}): {e}")
            
            time.sleep(1 * (attempt + 1))  # Backoff exponentiel
        
        return None

    # --- COMMANDES ADMIN ---
    def _handle_command_debug(self, chat_id: int):
        """Diagnostic complet"""
        if not self.card_predictor:
            self.send_message(chat_id, "❌ CardPredictor non chargé")
            return
        
        cp = self.card_predictor
        
        # Vérification des types
        verdicts = []
        if not isinstance(cp.predictions, dict):
            verdicts.append("❌ predictions n'est pas un dict")
        if not isinstance(cp.inter_data, list):
            verdicts.append("❌ inter_data n'est pas une liste")
        if not isinstance(cp.smart_rules, list):
            verdicts.append("❌ smart_rules n'est pas une liste")
        
        if verdicts:
            self.send_message(chat_id, "🔍 **DIAGNOSTIQUE:**\n" + "\n".join(verdicts))
            return
        
        pending = [p for p in cp.predictions.values() if p.get('status') == 'pending']
        active_rules = [r for r in cp.smart_rules if not r.get('quarantined')]
        
        msg = f"""
🔍 **DIAGNOSTIQUE SYSTEME**

📊 **Données:**
• Prédictions: {len(cp.predictions)} ({len(pending)} pending)
• Jeux collectés: {len(cp.inter_data)}
• Règles actives: {len(active_rules)}/16
• Quarantaine: {sum(len(q) for q in cp.quarantined_rules.values())}

⏰ **Session:**
• Heure: {cp.now().strftime('%H:%M:%S')}
• Active: {'✅' if cp.is_in_session() else '❌'}
• Mode INTER: {'✅' if cp.is_inter_mode_active else '❌'}

🎯 **State:**
• Dernier jeu: J{cp.last_predicted_game_number}
• Derniers costumes: {list(cp.last_suit_predictions)}
"""
        self.send_message(chat_id, msg)

    def _handle_command_inter(self, chat_id: int, text: str):
        """Gestion mode INTER"""
        if not self.card_predictor:
            return
        
        parts = text.lower().split()
        action = parts[1] if len(parts) > 1 else 'status'
        
        if action == 'activate':
            if len(self.card_predictor.inter_data) < 3:
                self.send_message(chat_id, f"⚠️ Données insuffisantes: {len(self.card_predictor.inter_data)}/3")
                return
            
            self.card_predictor.analyze_and_set_smart_rules(chat_id=chat_id, force_activate=True)
            self.send_message(chat_id, "✅ **MODE INTER ACTIVÉ**")
        
        elif action == 'default':
            self.card_predictor.is_inter_mode_active = False
            self.card_predictor._save_all_data()
            self.send_message(chat_id, "❌ **MODE INTER DÉSACTIVÉ**")
        
        else:
            self.send_message(chat_id, """
🤖 **INTER Commands:**
• `/inter status` - Voir statut
• `/inter activate` - ACTIVER
• `/inter default` - Désactiver
""")

    # --- GESTION MESSAGES SOURCE ---
    def _process_source_channel_message(self, message: Dict[str, Any]):
        """Traitement principal canal source"""
        try:
            text = message.get('text', '')
            chat_id = message['chat']['id']
            
            logger.info(f"\n{'='*50}")
            logger.info(f"📥 SOURCE: {text[:80]}")
            logger.info(f"{'='*50}")
            
            # 1. Vérifier prédictions en attente
            self._verify_pending_predictions(text)
            
            # 2. Collecter données
            game_num = self.card_predictor.extract_game_number_from_text(text)
            if game_num:
                self.card_predictor.collect_inter_data(game_num, text)
            
            # 3. Mettre à jour règles
            self.card_predictor.check_and_update_rules()
            
            # 4. Prédire si conditions remplies
            self._check_manual_prediction(text)
            
            logger.info("✅ Traitement terminé")
            
        except Exception as e:
            logger.error(f"❌ Erreur source: {e}", exc_info=True)

    def _check_manual_prediction(self, text: str):
        """Vérifie et prédit"""
        try:
            logger.info("🔍 Vérification prédiction")
            
            ok, game_num, suit, is_inter = self.card_predictor.should_predict(text)
            
            if ok and game_num and suit:
                logger.info(f"✅ Conditions remplies: J{game_num} → {suit}")
                
                can_predict, reason = self._can_make_prediction(game_num, suit)
                
                if can_predict:
                    logger.info(f"🚀 Envoi prédiction: J{game_num}")
                    
                    txt = self.card_predictor.prepare_prediction_text(game_num, suit)
                    mid = self.send_message(PREDICTION_CHANNEL_ID, txt)
                    
                    if mid:
                        trigger = getattr(self.card_predictor, '_last_trigger_used', '?')
                        rule_idx = getattr(self.card_predictor, '_last_rule_index', 0)
                        
                        self.card_predictor.make_prediction(
                            game_num, suit, mid, is_inter=is_inter,
                            trigger_used=trigger, rule_index=rule_idx
                        )
                        logger.info(f"✅ Prédiction envoyée: J{game_num} (ID: {mid})")
                else:
                    logger.warning(f"🚫 Prédiction bloquée: {reason}")
            else:
                logger.debug("🚫 Conditions non remplies")
        
        except Exception as e:
            logger.error(f"❌ Erreur prédiction: {e}", exc_info=True)

    def _can_make_prediction(self, game_num: int, suit: str) -> tuple[bool, str]:
        """Vérifie toutes les règles métier"""
        if not self.card_predictor:
            return False, "Moteur non chargé"
        
        # Vérifier écart 3+
        if not self.card_predictor._check_gap_rule(game_num):
            return False, f"Écart 3 non respecté (dernier: J{self.card_predictor.last_predicted_game_number})"
        
        # Vérifier anti-répétition
        if not self.card_predictor._check_suit_repetition(suit):
            return False, f"Costume {suit} déjà prédit 2x"
        
        return True, "✅ OK"

    def _verify_pending_predictions(self, text: str):
        """Vérifie et résout les prédictions en attente"""
        try:
            current_game = self.card_predictor.extract_game_number_from_text(text)
            if not current_game:
                return
            
            logger.info(f"🔍 Vérification jeu {current_game}")
            
            if not isinstance(self.card_predictor.predictions, dict):
                logger.error("❌ predictions corrompu")
                return
            
            for pred_game_num, prediction in list(self.card_predictor.predictions.items()):
                if not isinstance(prediction, dict):
                    continue
                
                if prediction.get('status') != 'pending':
                    continue
                
                for offset in [0, 1, 2]:
                    expected_game = int(pred_game_num) + offset
                    
                    if current_game == expected_game:
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
                                logger.info(f"✅ Prédiction J{pred_game_num} vérifiée")
                                break
        
        except Exception as e:
            logger.error(f"❌ Erreur vérification: {e}")

    def handle_update(self, update: Dict[str, Any]):
        """Point d'entrée principal"""
        if not self.card_predictor:
            logger.error("🚫 Handler non disponible")
            return
        
        try:
            # Vérifier bilans programmés
            self.card_predictor.check_and_send_scheduled_reports()
            
            # Router selon type
            if 'message' in update:
                self._process_message(update['message'])
            elif 'channel_post' in update:
                self._process_message(update['channel_post'])
            elif 'edited_message' in update:
                self._process_edited_message(update['edited_message'])
            elif 'callback_query' in update:
                self._handle_callback_query(update['callback_query'])
        
        except Exception as e:
            logger.critical(f"❌ Erreur critique update: {e}", exc_info=True)

    def _process_message(self, message: Dict[str, Any]):
        """Route un message"""
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
                self._handle_command_stat(chat_id)
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
            elif text.startswith('/start'):
                self.send_message(chat_id, WELCOME_MESSAGE)
                return
            
            # Canal source
            if str(chat_id) == str(self.card_predictor.target_channel_id):
                logger.debug(f"📍 Message source détecté")
                self._process_source_channel_message(message)
        
        except Exception as e:
            logger.error(f"❌ Erreur traitement message: {e}", exc_info=True)

    def _process_edited_message(self, edited_msg: Dict[str, Any]):
        """Traite message édité"""
        try:
            chat_id = edited_msg['chat']['id']
            text = edited_msg.get('text', '')
            
            if str(chat_id) == str(self.card_predictor.target_channel_id):
                # Collecter données
                game_num = self.card_predictor.extract_game_number_from_text(text)
                if game_num:
                    self.card_predictor.collect_inter_data(game_num, text)
                
                # Vérifier prédictions
                self._verify_pending_predictions(text)
        
        except Exception as e:
            logger.error(f"❌ Erreur message édité: {e}")
