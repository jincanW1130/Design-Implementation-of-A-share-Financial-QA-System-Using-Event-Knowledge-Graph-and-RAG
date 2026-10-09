-- ===========================================================================
-- 六张表.sql —— 第 9 阶段（前后端系统集成）MySQL 六张表的 DDL
-- ===========================================================================
-- 唯一规格：《10-系统总体设计（第四阶段）》第 4.4.1 节 表 4-6「六张表的字段级设计」
--           与 第 4.4.2 节「历史证据保护与关键约束」。字段名、类型、可空、键逐字对齐，
--           **不新增字段、不新增表**（《24-第9阶段任务书》第五节 硬约束 3）。
--
-- 三条硬口径（照《10》第 4.4.2 节的等价 SQL 片段落地）：
--   ① answer_evidence 的联合主键 PRIMARY KEY (answer_id, chunk_id)
--      ——「同一个文本块无论被哪一路命中都只算一个证据」在数据层的表达；
--   ② document_chunk 的 UNIQUE KEY uk_chunk_doc_index (doc_id, chunk_index)
--      与 UNIQUE KEY uk_chunk_vector_id (vector_id)；
--   ③ 六条外键；其中 fk_ae_chunk 与 fk_ae_doc 必须 ON DELETE RESTRICT
--      ——被 answer_evidence 引用过的文档与文本块禁止物理删除（B7 的数据库层兜底）。
--      其余四条：fk_chunk_doc 级联删除、fk_question_user 置空、
--      fk_answer_question 级联删除、fk_ae_answer 级联删除。
--
-- 引擎与字符集：ENGINE=InnoDB、DEFAULT CHARSET=utf8mb4、
--              COLLATE=utf8mb4_0900_ai_ci（《24》第2.4节 第 2 条）。
--
-- 落盘约定：
--   * 全部使用 CREATE TABLE IF NOT EXISTS（重复执行不报错，供 init_schema() 直接跑）；
--   * **本文件里不出现库名**（连注释里也不写）——库由脚本按 `config.local.json` 的
--     `mysql_database` 建（db.ensure_database()）；本文件只描述表，可由任意库承载。
--     这样「库名只有一处定义」，改库名不必动 DDL；
--   * 表内注释（COMMENT）**刻意不使用分号**，以免朴素语句切分器误切。
--   * `user` 与 `rank` 是 MySQL 的保留字／关键字，一律反引号包裹。
--
-- 与《10》表 4-6 的逐项对应见每张表前的行内注释；普通索引共 14 个：
--   idx_doc_publish_time／idx_doc_ingest_time／idx_doc_category／idx_chunk_doc_id／
--   idx_q_session_time(session_id, ask_time)／idx_q_task_type／idx_q_gold_hop_depth／
--   idx_q_time_constraint／idx_a_question_id／idx_a_create_time／idx_ae_answer_id／
--   idx_ae_doc_id／idx_ae_evidence_type／uk_user_username。
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. user —— 存储账号与登录信息；仅在启用登录功能时使用；第一版保持为空
--    对应表 4-6 的 4 个字段：user_id／username／password_hash／create_time
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user` (
  `user_id`       BIGINT       NOT NULL                COMMENT '用户标识：第一版不写入数据',
  `username`      VARCHAR(64)  NOT NULL                COMMENT '登录名：仅启用登录时使用',
  `password_hash` VARCHAR(255) NOT NULL                COMMENT '口令摘要：不保存明文口令',
  `create_time`   DATETIME     NOT NULL                COMMENT '记录创建时间',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uk_user_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='账号与登录信息：第一版不启用登录，表保持为空';

-- ---------------------------------------------------------------------------
-- 2. document —— 导入的财经文本及其元数据；向量化与事件抽取的数据来源
--    对应表 4-6 的 10 个字段
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `document` (
  `doc_id`       BIGINT        NOT NULL                     COMMENT '文档标识：向量—原文映射链路的终点编号',
  `title`        VARCHAR(512)  NOT NULL                     COMMENT '文档标题',
  `content`      LONGTEXT      NOT NULL                     COMMENT '文档正文：文本内容的权威来源',
  `source`       VARCHAR(128)  NOT NULL                     COMMENT '来源类型：区分公告、新闻与政策文件',
  `url`          VARCHAR(1024)     NULL                     COMMENT '原文链接：访问受限时保留其余元数据',
  `publish_time` DATETIME      NOT NULL                     COMMENT '文档发布时间：归属 Document 节点一侧',
  `ingest_time`  DATETIME      NOT NULL                     COMMENT '入库时间：由导入环节写入',
  `category`     VARCHAR(64)       NULL                     COMMENT '文档分类：与 source 共同区分来源类型',
  `company_list` VARCHAR(512)      NULL                     COMMENT '涉及公司的代码或名称列表',
  `create_time`  DATETIME      NOT NULL                     COMMENT '记录创建时间',
  PRIMARY KEY (`doc_id`),
  KEY `idx_doc_publish_time` (`publish_time`),
  KEY `idx_doc_ingest_time`  (`ingest_time`),
  KEY `idx_doc_category`     (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='导入的财经文本及其元数据';

-- ---------------------------------------------------------------------------
-- 3. document_chunk —— 文档切分后的文本块；向量检索与证据定位之间的中间层
--    对应表 4-6 的 6 个字段
--    约束：fk_chunk_doc（级联删除）、uk_chunk_doc_index、uk_chunk_vector_id
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `document_chunk` (
  `chunk_id`    BIGINT  NOT NULL              COMMENT '文本块标识：证据的最小单位',
  `doc_id`      BIGINT  NOT NULL              COMMENT '所属文档',
  `chunk_index` INT     NOT NULL              COMMENT '文本块在文档内的序号',
  `content`     TEXT    NOT NULL              COMMENT '文本块内容',
  `token_count` INT     NOT NULL              COMMENT '文本块 token 数：用于上下文预算裁剪',
  `vector_id`   BIGINT      NULL              COMMENT '向量在索引中的编号：未向量化时为空',
  PRIMARY KEY (`chunk_id`),
  UNIQUE KEY `uk_chunk_doc_index` (`doc_id`, `chunk_index`),
  UNIQUE KEY `uk_chunk_vector_id` (`vector_id`),
  KEY `idx_chunk_doc_id` (`doc_id`),
  CONSTRAINT `fk_chunk_doc` FOREIGN KEY (`doc_id`) REFERENCES `document` (`doc_id`)
    ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='文档切分后的文本块';

-- ---------------------------------------------------------------------------
-- 4. question —— 用户提交的问题；task_type／gold_hop_depth／time_constraint
--    为测试集标注字段，非测试集题目留空；session_id 是**本表字段而不是新表**
--    对应表 4-6 的 8 个字段
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `question` (
  `question_id`     BIGINT      NOT NULL            COMMENT '问题标识',
  `user_id`         BIGINT          NULL            COMMENT '提问用户：登录未启用时为空',
  `session_id`      CHAR(36)        NULL            COMMENT '浏览器生成的 UUID：用于按会话隔离历史记录',
  `question_text`   TEXT        NOT NULL            COMMENT '问题正文',
  `task_type`       VARCHAR(16)     NULL            COMMENT '测试集标注：事实型／事件型／关系型',
  `gold_hop_depth`  TINYINT         NULL            COMMENT '测试集标注：标注路径深度 0／1／2',
  `time_constraint` TINYINT         NULL            COMMENT '测试集标注：是否有时间约束 0／1',
  `ask_time`        DATETIME    NOT NULL            COMMENT '提问时间',
  PRIMARY KEY (`question_id`),
  KEY `idx_q_session_time`    (`session_id`, `ask_time`),
  KEY `idx_q_task_type`       (`task_type`),
  KEY `idx_q_gold_hop_depth`  (`gold_hop_depth`),
  KEY `idx_q_time_constraint` (`time_constraint`),
  CONSTRAINT `fk_question_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
    ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='用户提交的问题';

-- ---------------------------------------------------------------------------
-- 5. answer —— 系统生成的回答及其生成信息
--    对应表 4-6 的 8 个字段；graph_path 以 JSON 文本存储，不建独立路径表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `answer` (
  `answer_id`         BIGINT       NOT NULL              COMMENT '回答标识',
  `question_id`       BIGINT       NOT NULL              COMMENT '对应问题',
  `answer_text`       LONGTEXT     NOT NULL              COMMENT '回答正文',
  `graph_path`        JSON             NULL              COMMENT '使用的图谱路径：未使用图谱扩展时为空',
  `model_name`        VARCHAR(128) NOT NULL              COMMENT '生成模型标识：实验期间固定模型',
  `prompt_version`    VARCHAR(16)  NOT NULL              COMMENT 'Prompt 版本号：实验期间固定提示词',
  `is_graph_extended` TINYINT      NOT NULL              COMMENT '本次回答是否使用图谱扩展 0／1',
  `create_time`       DATETIME     NOT NULL              COMMENT '回答生成时间',
  PRIMARY KEY (`answer_id`),
  KEY `idx_a_question_id` (`question_id`),
  KEY `idx_a_create_time` (`create_time`),
  CONSTRAINT `fk_answer_question` FOREIGN KEY (`question_id`) REFERENCES `question` (`question_id`)
    ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='系统生成的回答及其生成信息';

-- ---------------------------------------------------------------------------
-- 6. answer_evidence —— 答案与证据文档、证据文本块之间的关联；证据追溯核心表
--    对应表 4-6 的 5 个字段
--    **联合主键 (answer_id, chunk_id)**；fk_ae_doc／fk_ae_chunk 为 RESTRICT
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `answer_evidence` (
  `answer_id`     BIGINT      NOT NULL              COMMENT '所属回答',
  `chunk_id`      BIGINT      NOT NULL              COMMENT '证据文本块',
  `doc_id`        BIGINT      NOT NULL              COMMENT '证据所属文档：与 chunk_id 冗余以支持按文档聚合',
  `rank`          INT         NOT NULL              COMMENT '该证据在最终证据集合中的序号',
  `evidence_type` VARCHAR(32) NOT NULL              COMMENT '证据类型：回答来源／新闻来源／公告来源／相关事件',
  PRIMARY KEY (`answer_id`, `chunk_id`),
  KEY `idx_ae_answer_id`     (`answer_id`),
  KEY `idx_ae_doc_id`        (`doc_id`),
  KEY `idx_ae_evidence_type` (`evidence_type`),
  CONSTRAINT `fk_ae_answer` FOREIGN KEY (`answer_id`) REFERENCES `answer` (`answer_id`)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_ae_chunk` FOREIGN KEY (`chunk_id`) REFERENCES `document_chunk` (`chunk_id`)
    ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_ae_doc` FOREIGN KEY (`doc_id`) REFERENCES `document` (`doc_id`)
    ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='答案与证据的关联：历史证据保护由 RESTRICT 外键兜底';
