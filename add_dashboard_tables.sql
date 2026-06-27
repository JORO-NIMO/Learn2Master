-- Create Topics Table
CREATE TABLE IF NOT EXISTS Topics (
    topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    difficulty_level TEXT CHECK(difficulty_level IN ('easy', 'medium', 'hard')),
    content_url TEXT
);

-- Create Progress Table
CREATE TABLE IF NOT EXISTS Progress (
    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    completion_status TEXT CHECK(completion_status IN ('not_started', 'in_progress', 'completed')) DEFAULT 'not_started',
    score INTEGER,
    FOREIGN KEY (learner_id) REFERENCES Learners(learner_id),
    FOREIGN KEY (topic_id) REFERENCES Topics(topic_id)
);