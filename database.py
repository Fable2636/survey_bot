import sqlite3
import json
import logging
from typing import Dict, List, Any, Optional, Union

class Database:
    """Класс для работы с базой данных SQLite"""
    
    def __init__(self, db_name="survey_bot.db"):
        """Инициализация базы данных"""
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Подключение к базе данных"""
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.conn.row_factory = sqlite3.Row  # Для доступа к данным по названиям столбцов
            self.cursor = self.conn.cursor()
            logging.info(f"Успешное подключение к базе данных {self.db_name}")
        except sqlite3.Error as e:
            logging.error(f"Ошибка подключения к базе данных: {e}")
    
    def create_tables(self):
        """Создание необходимых таблиц, если они не существуют"""
        try:
            # Таблица для хранения результатов опроса
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS survey_results (
                user_id INTEGER PRIMARY KEY,
                municipality TEXT,
                category TEXT,
                knows_movement TEXT,
                is_participant TEXT,
                knows_curator TEXT,
                selected_directions TEXT,
                region_rating TEXT,
                organization_rating TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            self.conn.commit()
            logging.info("Таблицы успешно созданы или уже существуют")
        except sqlite3.Error as e:
            logging.error(f"Ошибка создания таблиц: {e}")
    
    def save_survey_result(self, user_id: int, data: Dict[str, Any]) -> bool:
        """Сохранение или обновление результатов опроса пользователя"""
        try:
            # Преобразуем списки и другие сложные объекты в JSON строку
            processed_data = {}
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    processed_data[key] = json.dumps(value, ensure_ascii=False)
                else:
                    processed_data[key] = value
            
            # Проверяем, существует ли запись для этого пользователя
            self.cursor.execute("SELECT user_id FROM survey_results WHERE user_id = ?", (user_id,))
            exists = self.cursor.fetchone()
            
            if exists:
                # Обновляем существующую запись
                fields = []
                values = []
                
                for key, value in processed_data.items():
                    fields.append(f"{key} = ?")
                    values.append(value)
                
                # Добавляем user_id в конец списка значений
                values.append(user_id)
                
                query = f"UPDATE survey_results SET {', '.join(fields)} WHERE user_id = ?"
                self.cursor.execute(query, values)
            else:
                # Создаем новую запись
                fields = ["user_id"]
                placeholders = ["?"]
                values = [user_id]
                
                for key, value in processed_data.items():
                    fields.append(key)
                    placeholders.append("?")
                    values.append(value)
                
                query = f"INSERT INTO survey_results ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
                self.cursor.execute(query, values)
            
            self.conn.commit()
            logging.info(f"Результаты опроса для пользователя {user_id} успешно сохранены")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка при сохранении результатов опроса: {e}")
            return False
    
    def get_all_results(self) -> List[Dict[str, Any]]:
        """Получение всех результатов опроса"""
        try:
            self.cursor.execute("SELECT * FROM survey_results ORDER BY timestamp DESC")
            rows = self.cursor.fetchall()
            
            results = []
            for row in rows:
                result = dict(row)
                
                # Преобразуем JSON строки обратно в объекты Python
                for key, value in result.items():
                    if key == 'selected_directions' and value:
                        try:
                            result[key] = json.loads(value)
                        except:
                            result[key] = []
                
                results.append(result)
            
            return results
        except sqlite3.Error as e:
            logging.error(f"Ошибка при получении результатов опроса: {e}")
            return []
    
    def get_result_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение результатов опроса конкретного пользователя"""
        try:
            self.cursor.execute("SELECT * FROM survey_results WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            
            if row:
                result = dict(row)
                
                # Преобразуем JSON строки обратно в объекты Python
                for key, value in result.items():
                    if key == 'selected_directions' and value:
                        try:
                            result[key] = json.loads(value)
                        except:
                            result[key] = []
                
                return result
            return None
        except sqlite3.Error as e:
            logging.error(f"Ошибка при получении результатов пользователя {user_id}: {e}")
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики по опросу"""
        try:
            stats = {
                'total_users': 0,
                'municipalities': {},
                'categories': {},
                'knows_movement': {'Да': 0, 'Нет': 0, 'Не указано': 0},
                'is_participant': {'Да': 0, 'Нет': 0, 'Не указано': 0},
                'knows_curator': {'Да': 0, 'Нет': 0, 'Не указано': 0},
                'selected_directions': {},
                'region_rating': {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0, 'Не указано': 0},
                'organization_rating': {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0, 'Не указано': 0}
            }
            
            # Получаем все результаты
            results = self.get_all_results()
            stats['total_users'] = len(results)
            
            # Анализируем каждый результат
            for result in results:
                # Муниципалитеты
                municipality = result.get('municipality', 'Не указано')
                stats['municipalities'][municipality] = stats['municipalities'].get(municipality, 0) + 1
                
                # Категории
                category = result.get('category', 'Не указано')
                stats['categories'][category] = stats['categories'].get(category, 0) + 1
                
                # Знание о движении
                knows = result.get('knows_movement', 'Не указано')
                stats['knows_movement'][knows] = stats['knows_movement'].get(knows, 0) + 1
                
                # Участие в движении
                participant = result.get('is_participant', 'Не указано')
                stats['is_participant'][participant] = stats['is_participant'].get(participant, 0) + 1
                
                # Знание куратора
                curator = result.get('knows_curator', 'Не указано')
                stats['knows_curator'][curator] = stats['knows_curator'].get(curator, 0) + 1
                
                # Направления
                directions = result.get('selected_directions', [])
                if isinstance(directions, list):
                    for direction in directions:
                        stats['selected_directions'][direction] = stats['selected_directions'].get(direction, 0) + 1
                
                # Рейтинги
                region = result.get('region_rating', 'Не указано')
                stats['region_rating'][region] = stats['region_rating'].get(region, 0) + 1
                
                org = result.get('organization_rating', 'Не указано')
                stats['organization_rating'][org] = stats['organization_rating'].get(org, 0) + 1
            
            return stats
        except Exception as e:
            logging.error(f"Ошибка при получении статистики: {e}")
            return {
                'total_users': 0,
                'error': str(e)
            }
    
    def delete_result(self, user_id: int) -> bool:
        """Удаление результатов опроса пользователя"""
        try:
            self.cursor.execute("DELETE FROM survey_results WHERE user_id = ?", (user_id,))
            self.conn.commit()
            logging.info(f"Результаты пользователя {user_id} успешно удалены")
            return True
        except sqlite3.Error as e:
            logging.error(f"Ошибка при удалении результатов пользователя {user_id}: {e}")
            return False
    
    def close(self):
        """Закрытие соединения с базой данных"""
        if self.conn:
            self.conn.close()
            logging.info("Соединение с базой данных закрыто") 