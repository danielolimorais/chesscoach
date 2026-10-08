import sqlite3
import chess
from evaluator import StockfishEvaluator

class PatternAnalyzer:
    def __init__(self, db_path="chesscoach.db"):
        self.db_path = db_path
        self.evaluator = StockfishEvaluator(stockfish_path="./stockfish.exe")

    def _get_games(self, limit=30):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, played_at, color, result 
                FROM games 
                ORDER BY played_at DESC 
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def _get_moves_for_game(self, game_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ply, san, fen_before 
                FROM moves 
                WHERE game_id = ? 
                ORDER BY ply
            """, (game_id,))
            return cursor.fetchall()
            
    def run_batch_analysis(self, num_games=30):
        games = self._get_games(limit=num_games)
        print(f"A iniciar análise em lote de {len(games)} partidas...")
        
        stats = {
            "total_games_analyzed": 0,
            "total_user_moves": 0,
            "total_cp_loss": 0,
            "blunders": 0,
            "mistakes": 0,
            "inaccuracies": 0,
            "color_stats": {
                "White": {"moves": 0, "cp_loss": 0},
                "Black": {"moves": 0, "cp_loss": 0}
            }
        }

        for game in games:
            game_id, played_at, user_color_str, result = game
            # Normaliza a cor do utilizador para corresponder ao python-chess
            user_color = "White" if user_color_str.lower() == "white" else "Black"
            
            moves = self._get_moves_for_game(game_id)
            if not moves:
                continue
                
            stats["total_games_analyzed"] += 1
            print(f"A analisar partida {stats['total_games_analyzed']}/{len(games)}...")
            
            for ply, played_move, fen in moves:
                turn_color = "White" if ply % 2 != 0 else "Black"
                
                # Só analisamos a Perda de Centipeões (ACPL) nos SEUS lances
                if turn_color != user_color:
                    continue
                    
                eval_before = self.evaluator.get_evaluation(fen)
                board = chess.Board(fen)
                board.push_san(played_move)
                eval_after = self.evaluator.get_evaluation(board.fen())
                
                if eval_before["score_cp"] is not None and eval_after["score_cp"] is not None:
                    if turn_color == "White":
                        cp_loss = eval_before["score_cp"] - eval_after["score_cp"]
                    else:
                        cp_loss = eval_after["score_cp"] - eval_before["score_cp"]
                        
                    # Previne perdas negativas causadas por ganhos forçados ou bugs de transição
                    cp_loss = max(0, cp_loss)
                    
                    stats["total_user_moves"] += 1
                    stats["total_cp_loss"] += cp_loss
                    stats["color_stats"][turn_color]["moves"] += 1
                    stats["color_stats"][turn_color]["cp_loss"] += cp_loss
                    
                    if cp_loss >= 200:
                        stats["blunders"] += 1
                    elif cp_loss >= 80:
                        stats["mistakes"] += 1
                    elif cp_loss >= 30:
                        stats["inaccuracies"] += 1

        # Calcular as Médias (ACPL - Average Centipawn Loss)
        stats["acpl_overall"] = stats["total_cp_loss"] // stats["total_user_moves"] if stats["total_user_moves"] > 0 else 0
        
        w_moves = stats["color_stats"]["White"]["moves"]
        stats["color_stats"]["White"]["acpl"] = stats["color_stats"]["White"]["cp_loss"] // w_moves if w_moves > 0 else 0
        
        b_moves = stats["color_stats"]["Black"]["moves"]
        stats["color_stats"]["Black"]["acpl"] = stats["color_stats"]["Black"]["cp_loss"] // b_moves if b_moves > 0 else 0

        print("Análise em lote concluída!")
        return stats

if __name__ == "__main__":
    analyzer = PatternAnalyzer()
    resultado = analyzer.run_batch_analysis(num_games=10) # Testamos com 10 para ser mais rápido
    print(resultado)