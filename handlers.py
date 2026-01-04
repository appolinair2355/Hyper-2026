import logging
from typing import Dict, Any, List, Optional
import time
import re
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class TelegramHandlers:
    def __init__(self, bot_instance, card_predictor_instance):
        self.bot = bot_instance
        self.card_predictor = card_predictor_instance
        self.admin_id = None
        self.last_user_interaction = {} # user_id -> timestamp
        # Fix pour card_predictor qui utilise cette méthode
        if self.card_predictor:
            self.card_predictor.telegram_message_sender = self.send_message

    def set_admin_id(self, admin_id):
        self.admin_id = admin_id

    def send_message(self, chat_id: int, text: str):
        if self.bot and chat_id:
            try:
                # Utiliser l'API directe du bot sans passer par les handlers pour éviter la récursion
                url = f"https://api.telegram.org/bot{self.bot.token}/sendMessage"
                data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
                import requests
                requests.post(url, json=data, timeout=10)
            except Exception as e:
                logger.error(f"❌ Erreur envoi message direct: {e}")

    def _check_rate_limit(self, user_id: int) -> bool:
        now = time.time()
        last = self.last_user_interaction.get(user_id, 0)
        if now - last < 1: # 1 seconde entre les commandes
            return False
        self.last_user_interaction[user_id] = now
        return True

    def handle_update(self, update: Dict[str, Any]):
        """Point d'entrée principal pour tous les webhooks Telegram"""
        try:
            # 1. BILANS HORAIRES
            if self.card_predictor:
                self.card_predictor.check_and_send_scheduled_reports()

            # 2. CANAUX (Source de données)
            if 'channel_post' in update:
                post = update['channel_post']
                chat_id = post.get('chat', {}).get('id')
                text = post.get('text', '')
                if text and str(chat_id) == str(self.card_predictor.target_channel_id):
                    self._process_source_channel_message(post)
                return

            # 3. COMMANDES (Messages Privés)
            if 'message' in update:
                msg = update['message']
                if msg.get('text'):
                    self._process_message(msg)
                return
        except Exception as e:
            logger.error(f"❌ ERREUR handle_update: {e}", exc_info=True)

    def _process_message(self, message: Dict[str, Any]):
        """Traite un message privé"""
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '')
            user_id = message.get('from', {}).get('id', 0)
            
            if not self._check_rate_limit(user_id): return
            
            if text.startswith('/inter'): self._handle_command_inter(chat_id, text)
            elif text.startswith('/deploy'): self._handle_command_deploy(chat_id)
            elif text.startswith('/collect'): self._handle_command_collect(chat_id)
            elif text.startswith('/qua'): self._handle_command_qua(chat_id)
            elif text.startswith('/reset'): self._handle_command_reset(chat_id)
            elif text.startswith('/bilan'): self._handle_command_bilan(chat_id)
            elif text.startswith('/start'): self.send_message(chat_id, "🤖 **Bot Joker Prêt**")
        except Exception as e:
            logger.error(f"❌ Erreur _process_message: {e}")

    def _process_source_channel_message(self, post: Dict[str, Any]):
        """Traite un message du canal source"""
        try:
            text = post.get('text', '')
            game_num = self.card_predictor.extract_game_number(text)
            if not game_num: return

            logger.info(f"📥 Jeu #{game_num}")
            self.card_predictor.collect_inter_data(game_num, text)
            
            # Vérif
            result = self.card_predictor.verify_prediction(game_num, text)
            if result and self.card_predictor.prediction_channel_id:
                sym = result.get('status_symbol', '❌')
                msg = f"🎯 Jeu #{game_num}\nRésultat: {sym}"
                self.send_message(self.card_predictor.prediction_channel_id, msg)

            # Pred
            pred = self.card_predictor.make_prediction(game_num, text)
            if pred and self.card_predictor.prediction_channel_id:
                msg = f"🚨 **PRÉDICTION JEU #{pred['target_game']}**\n\n💎 ENSEIGNE: {pred['predicted_suit']}\n🎰 Type: {pred['type']}\n📈 Status: Analyse..."
                self.send_message(self.card_predictor.prediction_channel_id, msg)
        except Exception as e:
            logger.error(f"❌ Erreur _process_source: {e}")

    def _handle_command_inter(self, chat_id: int, text: str):
        if not self.card_predictor: return
        self.card_predictor.is_inter_mode_active = not self.card_predictor.is_inter_mode_active
        status = "ACTIF" if self.card_predictor.is_inter_mode_active else "INACTIF"
        self.send_message(chat_id, f"🧠 Système Inter: {status}")

    def _handle_command_deploy(self, chat_id: int):
        import zipfile
        import os
        
        try:
            files_to_zip = [
                'main.py', 'bot.py', 'handlers.py', 'card_predictor.py', 
                'config.py', 'requirements.txt', 'runtime.txt', 'render.yaml'
            ]
            
            zip_filename = 'noooo.zip'
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for file in files_to_zip:
                    if os.path.exists(file):
                        zipf.write(file)
            
            if self.bot:
                self.bot.send_document(chat_id, zip_filename)
                self.send_message(chat_id, "✅ Package de déploiement Render.com généré et envoyé sous le nom 'noooo.zip'.")
        except Exception as e:
            logger.error(f"❌ Erreur déploiement: {e}")
            self.send_message(chat_id, f"❌ Erreur lors de la génération du package: {e}")

    def _handle_command_collect(self, chat_id: int):
        self.send_message(chat_id, "📥 Collecte manuelle lancée.")

    def _handle_command_qua(self, chat_id: int):
        if not self.card_predictor: return
        
        active = self.card_predictor._get_active_rules()
        q = self.card_predictor.quarantined_rules
        
        # 1. En-tête et Quarantaine
        msg = "🔒 **ÉTAT ET INFORMATIQUE SECRET DU BOT**\n\n"
        msg += "🔒 **TOP EN QUARANTAINE:**\n"
        has_q = False
        for suit, triggers in q.items():
            if triggers:
                for t, c in triggers.items():
                    has_q = True
                    msg += f"  • {t} → {suit}\n"
        if not has_q: msg += "  _Vide_\n"
        
        # 2. Dernières prédictions
        msg += "\n📊 **Les 5 dernières prédictions envoyées**\n"
        preds = sorted(self.card_predictor.predictions.items(), key=lambda x: x[1].get('timestamp', 0), reverse=True)[:5]
        if not preds:
            msg += "  _Aucune prédiction_\n"
        for game_num, p in preds:
            status_sym = "⏳" if p['status'] == 'pending' else ("✅" if p['status'] == 'won' else "❌")
            mode_sym = "🧠 INTER" if p['type'] == 'INTER' else "📋 STATIQUE"
            msg += f"  • Jeu {game_num}: {p['predicted_suit']} ({status_sym}) - Déclencheur: {p.get('trigger_card', '??')} {mode_sym}\n"
        
        # 3. Prochain bilan (Estimation)
        now = self.card_predictor.now()
        next_bilans = [6, 12, 18, 0]
        next_hour = next((h for h in next_bilans if h > now.hour), 0)
        diff_hours = (next_hour - now.hour) % 24
        msg += f"\n⏰ Prochain bilan dans: ~{diff_hours}h\n"
        
        # 4. État INTER
        status = "✅ ACTIF" if self.card_predictor.is_inter_mode_active else "❌ INACTIF"
        msg += f"\n🧠 Mode INTER: {status}\n"
        
        # 5. Statistiques
        msg += f"\n📈 Donnees collectees: {len(self.card_predictor.collected_games)} jeux\n"
        msg += "📋 **Regles UTILISER INTELLIGENT :**\n"
        
        smart_rules = self.card_predictor.smart_rules
        for suit in ['♠️', '❤️', '♦️', '♣️']:
            msg += f"\nPour predire {suit}:\n"
            suit_rules = [r for r in smart_rules if isinstance(r, dict) and r.get('predict') == suit]
            if not suit_rules:
                msg += "  _Aucune_\n"
            for r in suit_rules[:3]:
                msg += f"  • {r['trigger']} ({r['count']}x)\n"
                
        self.send_message(chat_id, msg)

    def _handle_command_reset(self, chat_id: int):
        if self.card_predictor:
            self.card_predictor.inter_data = []
            self.card_predictor.quarantined_rules = {}
            self.card_predictor._save_all_data()
            self.send_message(chat_id, "♻️ Réinitialisation effectuée.")

    def _handle_command_bilan(self, chat_id: int):
        if self.card_predictor:
            report = self.card_predictor.generate_full_report(self.card_predictor.now())
            self.send_message(chat_id, report)
