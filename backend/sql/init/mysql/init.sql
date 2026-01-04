-- ============================================
-- MySQL/MariaDB 校园交易系统完整数据库脚本
-- ============================================
-- 版本: 2.1
-- 日期: 2025-12-01
-- 说明: 包含所有表、索引、触发器、存储过程

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================
-- 1. 核心业务表
-- ============================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL COMMENT '用户名',
    email VARCHAR(100) UNIQUE NOT NULL COMMENT '校园邮箱',
    student_id VARCHAR(20) UNIQUE COMMENT '学号',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    phone VARCHAR(20) COMMENT '手机号',
    avatar_url VARCHAR(500) COMMENT '头像URL',
    real_name VARCHAR(50) COMMENT '真实姓名',
    is_active BOOLEAN DEFAULT TRUE COMMENT '账号是否激活',
    is_verified BOOLEAN DEFAULT FALSE COMMENT '是否实名认证',
    is_banned BOOLEAN DEFAULT FALSE COMMENT '是否被封禁',
    credit_score INT DEFAULT 100 COMMENT '信用分(0-100)',
    seller_rating DECIMAL(3,2) DEFAULT 5.00 COMMENT '卖家评分(0-5)',
    buyer_rating DECIMAL(3,2) DEFAULT 5.00 COMMENT '买家评分(0-5)',
    total_sales INT DEFAULT 0 COMMENT '总销售数',
    total_purchases INT DEFAULT 0 COMMENT '总购买数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,
    sync_version INT DEFAULT 0 COMMENT '同步版本号',
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本), 例: {"N":1,"S":0}',
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_student_id (student_id),
    INDEX idx_credit (credit_score),
    INDEX idx_active (is_active, is_banned)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 角色表 (RBAC)
CREATE TABLE IF NOT EXISTS roles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE COMMENT '角色名称',
    description VARCHAR(255) COMMENT '角色描述',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 1,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色表';

-- 权限表 (RBAC)
CREATE TABLE IF NOT EXISTS permissions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE COMMENT '权限名称',
    resource VARCHAR(50) NOT NULL COMMENT '资源类型',
    action VARCHAR(50) NOT NULL COMMENT '操作类型',
    description VARCHAR(255) COMMENT '权限描述',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 1,
    INDEX idx_name (name),
    INDEX idx_resource_action (resource, action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='权限表';

-- 用户角色关联表
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 1,
    UNIQUE KEY uq_user_role (user_id, role_id),
    INDEX idx_user (user_id),
    INDEX idx_role (role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户角色关联表';

-- 角色权限关联表
CREATE TABLE IF NOT EXISTS role_permissions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    role_id BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 1,
    UNIQUE KEY uq_role_permission (role_id, permission_id),
    INDEX idx_role (role_id),
    INDEX idx_permission (permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色权限关联表';

-- 用户资料表
CREATE TABLE IF NOT EXISTS user_profiles (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL COMMENT '显示名称',
    phone VARCHAR(32) COMMENT '联系电话',
    campus VARCHAR(120) COMMENT '校区',
    bio VARCHAR(500) COMMENT '个人简介',
    avatar_url VARCHAR(512) COMMENT '头像URL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 1,
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本)',
    INDEX idx_user (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户资料表';

-- 商品分类表
CREATE TABLE IF NOT EXISTS categories (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL COMMENT '分类名称',
    slug VARCHAR(50) UNIQUE NOT NULL COMMENT '分类标识',
    description TEXT COMMENT '分类描述',
    icon VARCHAR(100) COMMENT '图标',
    sort_order INT DEFAULT 0 COMMENT '排序',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_slug (slug),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品分类表';

-- 校区表
CREATE TABLE IF NOT EXISTS campuses (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL COMMENT '校区名称',
    code VARCHAR(20) UNIQUE NOT NULL COMMENT '校区代码(main/south/north)',
    address VARCHAR(200) COMMENT '地址',
    description TEXT COMMENT '描述',
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_code (code),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校区表';

-- 商品表
CREATE TABLE IF NOT EXISTS items (
    id BIGINT PRIMARY KEY,
    seller_id BIGINT NOT NULL COMMENT '卖家ID',
    category_id BIGINT COMMENT '分类ID',
    campus_id BIGINT COMMENT '校区ID',
    title VARCHAR(200) NOT NULL COMMENT '商品标题',
    description TEXT COMMENT '商品描述',
    price DECIMAL(10, 2) NOT NULL COMMENT '价格',
    original_price DECIMAL(10, 2) COMMENT '原价',
    condition_type ENUM('全新', '99新', '95新', '9成新', '二手') DEFAULT '二手' COMMENT '成色',
    location VARCHAR(100) COMMENT '交易地点',
    contact_info VARCHAR(200) COMMENT '联系方式(加密)',
    tags JSON COMMENT '商品标签数组',
    status ENUM('available', 'reserved', 'sold', 'deleted') DEFAULT 'available' COMMENT '商品状态',
    is_negotiable BOOLEAN DEFAULT FALSE COMMENT '是否可议价',
    is_shipped BOOLEAN DEFAULT FALSE COMMENT '是否包邮',
    view_count INT DEFAULT 0 COMMENT '浏览量',
    favorite_count INT DEFAULT 0 COMMENT '收藏量',
    inquiry_count INT DEFAULT 0 COMMENT '咨询量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sold_at TIMESTAMP NULL COMMENT '售出时间',
    sync_version INT DEFAULT 0,
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本)',
    INDEX idx_seller (seller_id),
    INDEX idx_category (category_id),
    INDEX idx_campus (campus_id),
    INDEX idx_status (status),
    INDEX idx_status_category_campus (status, category_id, campus_id),
    INDEX idx_created (created_at),
    INDEX idx_price (price),
    FULLTEXT idx_title_desc (title, description),
    FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (campus_id) REFERENCES campuses(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';

-- 商品图片表
CREATE TABLE IF NOT EXISTS item_images (
    id BIGINT PRIMARY KEY,
    item_id BIGINT NOT NULL,
    image_url VARCHAR(500) NOT NULL COMMENT '图片URL',
    sort_order INT DEFAULT 0 COMMENT '排序',
    is_cover BOOLEAN DEFAULT FALSE COMMENT '是否封面',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本)',
    INDEX idx_item (item_id),
    INDEX idx_cover (item_id, is_cover),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品图片表';


-- 购物车表
CREATE TABLE IF NOT EXISTS cart_items (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '用户ID',
    item_id BIGINT NOT NULL COMMENT '商品ID',
    quantity INT NOT NULL DEFAULT 1 COMMENT '数量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cart_user_item (user_id, item_id),
    INDEX idx_cart_user_id (user_id),
    INDEX idx_cart_item_id (item_id),
    INDEX idx_cart_created (created_at),
    CONSTRAINT fk_cart_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_cart_item FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='购物车表';


-- 交易表 (不使用分区，因为MySQL分区不支持外键)
CREATE TABLE IF NOT EXISTS transactions (
    id BIGINT PRIMARY KEY,
    item_id BIGINT NOT NULL,
    buyer_id BIGINT NOT NULL,
    seller_id BIGINT NOT NULL,
    item_price DECIMAL(10, 2) NOT NULL COMMENT '商品价格',
    final_amount DECIMAL(10, 2) NOT NULL COMMENT '最终成交价',
    status ENUM('pending', 'contacted', 'meeting', 'completed', 'cancelled') DEFAULT 'pending' COMMENT '交易状态',
    buyer_contact VARCHAR(200) COMMENT '买家联系方式(加密)',
    seller_contact VARCHAR(200) COMMENT '卖家联系方式(加密)',
    meeting_location VARCHAR(200) COMMENT '约定见面地点',
    meeting_time TIMESTAMP NULL COMMENT '约定见面时间',
    buyer_rating TINYINT COMMENT '买家评分1-5',
    seller_rating TINYINT COMMENT '卖家评分1-5',
    buyer_review TEXT COMMENT '买家评价',
    seller_review TEXT COMMENT '卖家评价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '交易创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    contacted_at TIMESTAMP NULL COMMENT '获取联系方式时间',
    completed_at TIMESTAMP NULL COMMENT '交易完成时间',
    cancelled_at TIMESTAMP NULL COMMENT '取消时间',
    sync_version INT DEFAULT 0,
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本)',
    INDEX idx_buyer (buyer_id),
    INDEX idx_seller (seller_id),
    INDEX idx_status_seller_amount (status, seller_id, final_amount),
    INDEX idx_item (item_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (buyer_id) REFERENCES users(id),
    FOREIGN KEY (seller_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易表';

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT PRIMARY KEY,
    sender_id BIGINT NOT NULL,
    receiver_id BIGINT NOT NULL,
    item_id BIGINT COMMENT '关联商品',
    content TEXT NOT NULL COMMENT '消息内容',
    is_read BOOLEAN DEFAULT FALSE,
    is_deleted_by_sender BOOLEAN DEFAULT FALSE,
    is_deleted_by_receiver BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    read_at TIMESTAMP NULL,
    sync_version INT DEFAULT 0,
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本)',
    INDEX idx_sender (sender_id),
    INDEX idx_receiver (receiver_id),
    INDEX idx_conversation (sender_id, receiver_id),
    INDEX idx_item (item_id),
    INDEX idx_created (created_at),
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息表';

-- 会话表（消息聊天）
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT PRIMARY KEY,
    user1_id BIGINT NOT NULL COMMENT '用户1 ID',
    user2_id BIGINT NOT NULL COMMENT '用户2 ID',
    item_id BIGINT NULL COMMENT '关联商品ID（可选）',
    last_message_id BIGINT NULL COMMENT '最后一条消息ID',
    last_message_content TEXT NULL COMMENT '最后消息内容',
    last_message_at TIMESTAMP NULL COMMENT '最后消息时间',
    user1_unread_count INT NOT NULL DEFAULT 0 COMMENT '用户1未读消息数',
    user2_unread_count INT NOT NULL DEFAULT 0 COMMENT '用户2未读消息数',
    user1_deleted BOOLEAN NOT NULL DEFAULT FALSE COMMENT '用户1是否删除',
    user2_deleted BOOLEAN NOT NULL DEFAULT FALSE COMMENT '用户2是否删除',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_conversation (user1_id, user2_id),
    INDEX idx_user1 (user1_id),
    INDEX idx_user2 (user2_id),
    INDEX idx_item (item_id),
    INDEX idx_updated (updated_at),
    FOREIGN KEY (user1_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user2_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL,
    FOREIGN KEY (last_message_id) REFERENCES messages(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话表（消息聊天）';

-- 收藏表
CREATE TABLE IF NOT EXISTS favorites (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    v_clock TEXT NULL COMMENT '向量时钟(JSON文本)',
    UNIQUE KEY uk_user_item (user_id, item_id),
    INDEX idx_user (user_id),
    INDEX idx_item (item_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='收藏表';


-- ============================================
-- 2. 系统管理表
-- ============================================


-- 系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT,
    description TEXT,
    is_public BOOLEAN DEFAULT FALSE COMMENT '是否公开',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统配置表';

-- 系统运行时设置表（管理员后台 Settings 使用；Hub-only）
CREATE TABLE IF NOT EXISTS system_settings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    category VARCHAR(64) NOT NULL COMMENT '设置分类',
    `key` VARCHAR(128) NOT NULL COMMENT '设置键',
    value JSON NOT NULL COMMENT '配置内容(JSON)',
    updated_by BIGINT NULL COMMENT '最后修改人',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_system_settings_category_key (category, `key`),
    INDEX ix_system_settings_category (category),
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统运行时设置表';

-- ============================================
-- 3. 触发器 (先删除再创建)
-- ============================================

DROP TRIGGER IF EXISTS trg_before_item_view_update;
DROP TRIGGER IF EXISTS trg_after_transaction_complete;
DROP TRIGGER IF EXISTS trg_after_favorite_insert;
DROP TRIGGER IF EXISTS trg_after_favorite_delete;
DROP TRIGGER IF EXISTS trg_after_transaction_rating;

DELIMITER //

CREATE TRIGGER trg_before_item_view_update
BEFORE UPDATE ON items
FOR EACH ROW
BEGIN
    IF NEW.view_count != OLD.view_count THEN
        SET NEW.updated_at = CURRENT_TIMESTAMP;
    END IF;
END//

CREATE TRIGGER trg_after_transaction_complete
AFTER UPDATE ON transactions
FOR EACH ROW
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        UPDATE users SET total_sales = total_sales + 1 WHERE id = NEW.seller_id;
        UPDATE users SET total_purchases = total_purchases + 1 WHERE id = NEW.buyer_id;
        UPDATE items SET status = 'sold', sold_at = CURRENT_TIMESTAMP WHERE id = NEW.item_id;
    END IF;
END//


CREATE TRIGGER trg_after_favorite_insert
AFTER INSERT ON favorites
FOR EACH ROW
BEGIN
    UPDATE items SET favorite_count = favorite_count + 1 WHERE id = NEW.item_id;
END//

CREATE TRIGGER trg_after_favorite_delete
AFTER DELETE ON favorites
FOR EACH ROW
BEGIN
    UPDATE items SET favorite_count = GREATEST(favorite_count - 1, 0) WHERE id = OLD.item_id;
END//

CREATE TRIGGER trg_after_transaction_rating
AFTER UPDATE ON transactions
FOR EACH ROW
BEGIN
    IF NEW.seller_rating IS NOT NULL AND OLD.seller_rating IS NULL THEN
        UPDATE users 
        SET seller_rating = (
            SELECT AVG(seller_rating) 
            FROM transactions 
            WHERE seller_id = NEW.seller_id AND seller_rating IS NOT NULL
        )
        WHERE id = NEW.seller_id;
    END IF;
    IF NEW.buyer_rating IS NOT NULL AND OLD.buyer_rating IS NULL THEN
        UPDATE users 
        SET buyer_rating = (
            SELECT AVG(buyer_rating) 
            FROM transactions 
            WHERE buyer_id = NEW.buyer_id AND buyer_rating IS NOT NULL
        )
        WHERE id = NEW.buyer_id;
    END IF;
END//

DELIMITER ;

-- ============================================
-- 4. 存储过程 (先删除再创建)
-- ============================================

DROP PROCEDURE IF EXISTS sp_create_transaction;
DROP PROCEDURE IF EXISTS sp_get_user_stats;
DROP PROCEDURE IF EXISTS sp_search_items;

DELIMITER //

CREATE PROCEDURE sp_create_transaction(
    IN p_tx_id BIGINT,
    IN p_item_id BIGINT,
    IN p_buyer_id BIGINT,
    IN p_buyer_contact VARCHAR(200),
    OUT p_transaction_id BIGINT,
    OUT p_error_msg VARCHAR(500)
)
BEGIN
    DECLARE v_seller_id BIGINT;
    DECLARE v_item_price DECIMAL(10,2);
    DECLARE v_item_status VARCHAR(20);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_error_msg = 'Transaction failed';
        SET p_transaction_id = NULL;
    END;
    
    START TRANSACTION;
    
    SELECT seller_id, price, status INTO v_seller_id, v_item_price, v_item_status
    FROM items WHERE id = p_item_id FOR UPDATE;
    
    IF v_item_status != 'available' THEN
        ROLLBACK;
        SET p_error_msg = '商品已下架或售出';
        SET p_transaction_id = NULL;
    ELSE
        INSERT INTO transactions (
            id, item_id, buyer_id, seller_id, item_price, final_amount, 
            buyer_contact, status, contacted_at
        ) VALUES (
            p_tx_id, p_item_id, p_buyer_id, v_seller_id, v_item_price, v_item_price,
            p_buyer_contact, 'contacted', CURRENT_TIMESTAMP
        );

        SET p_transaction_id = p_tx_id;
        UPDATE items SET status = 'reserved' WHERE id = p_item_id;
        COMMIT;
        SET p_error_msg = NULL;
    END IF;
END//

CREATE PROCEDURE sp_get_user_stats(IN p_user_id BIGINT)
BEGIN
    SELECT 
        u.username,
        u.credit_score,
        u.seller_rating,
        u.buyer_rating,
        u.total_sales,
        u.total_purchases,
        COUNT(DISTINCT i.id) AS active_items,
        COUNT(DISTINCT f.id) AS favorites_count,
        COUNT(DISTINCT t.id) AS transaction_count
    FROM users u
    LEFT JOIN items i ON i.seller_id = u.id AND i.status = 'available'
    LEFT JOIN favorites f ON f.user_id = u.id
    LEFT JOIN transactions t ON (t.buyer_id = u.id OR t.seller_id = u.id)
    WHERE u.id = p_user_id
    GROUP BY u.id, u.username, u.credit_score, u.seller_rating, u.buyer_rating, u.total_sales, u.total_purchases;
END//

CREATE PROCEDURE sp_search_items(
    IN p_keyword VARCHAR(200),
    IN p_category_id BIGINT,
    IN p_min_price DECIMAL(10,2),
    IN p_max_price DECIMAL(10,2),
    IN p_condition_type VARCHAR(20),
    IN p_offset INT,
    IN p_limit INT
)
BEGIN
    SELECT 
        i.*,
        u.username AS seller_username,
        u.seller_rating,
        u.is_verified,
        c.name AS category_name,
        (SELECT image_url FROM item_images WHERE item_id = i.id AND is_cover = TRUE LIMIT 1) AS cover_image
    FROM items i
    INNER JOIN users u ON i.seller_id = u.id
    LEFT JOIN categories c ON i.category_id = c.id
    WHERE i.status = 'available'
        AND (p_keyword IS NULL OR MATCH(i.title, i.description) AGAINST(p_keyword IN NATURAL LANGUAGE MODE))
        AND (p_category_id IS NULL OR i.category_id = p_category_id)
        AND (p_min_price IS NULL OR i.price >= p_min_price)
        AND (p_max_price IS NULL OR i.price <= p_max_price)
        AND (p_condition_type IS NULL OR i.condition_type = p_condition_type)
    ORDER BY i.created_at DESC
    LIMIT p_offset, p_limit;
END//

DELIMITER ;

-- ============================================
-- 5. 初始化数据
-- ============================================

INSERT INTO categories (name, slug, description, sort_order) VALUES
('全部', 'all', '所有商品', 0),
('数码产品', 'electronics', '电脑、手机、平板等', 1),
('图书教材', 'books', '教材、课外书、杂志等', 2),
('生活用品', 'daily', '日用品、家居用品', 3),
('运动装备', 'sports', '运动器材、健身用品', 4),
('服装鞋包', 'fashion', '衣服、鞋子、包包', 5),
('美妆护肤', 'beauty', '化妆品、护肤品', 6),
('票券卡劵', 'tickets', '优惠券、会员卡等', 7),
('其他', 'other', '其他商品', 99)
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT IGNORE INTO campuses (id, name, code, address, description, is_active, sort_order, created_at, updated_at, sync_version) VALUES
(1, '主校区', 'main', NULL, '默认主校区', 1, 0, NOW(), NOW(), 1),
(2, '南校区', 'south', NULL, '南校区', 1, 1, NOW(), NOW(), 1);

INSERT INTO system_configs (config_key, config_value, description, is_public) VALUES
('platform_name', '校园交易平台', '平台名称', TRUE),
('max_item_images', '5', '商品最多图片数', TRUE),
('min_credit_score', '60', '最低信用分', TRUE),
('transaction_timeout_hours', '24', '交易超时时间(小时)', FALSE),
('ban_credit_score', '30', '封号信用分阈值', FALSE)
ON DUPLICATE KEY UPDATE config_value=VALUES(config_value);

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================
-- 6. 视图
-- ============================================

CREATE OR REPLACE VIEW v_item_details AS
SELECT 
    i.id,
    i.title,
    i.description,
    i.price,
    i.original_price,
    i.condition_type,
    i.location,
    i.status,
    i.is_negotiable,
    i.is_shipped,
    i.view_count,
    i.favorite_count,
    i.inquiry_count,
    i.created_at,
    u.id AS seller_id,
    u.username AS seller_username,
    u.avatar_url AS seller_avatar,
    u.seller_rating,
    u.is_verified AS seller_verified,
    u.total_sales AS seller_total_sales,
    c.name AS category_name,
    c.slug AS category_slug
FROM items i
INNER JOIN users u ON i.seller_id = u.id
LEFT JOIN categories c ON i.category_id = c.id;

CREATE OR REPLACE VIEW v_transaction_stats AS
SELECT 
    DATE(created_at) AS transaction_date,
    COUNT(*) AS total_count,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_count,
    SUM(final_amount) AS total_amount,
    AVG(final_amount) AS avg_amount
FROM transactions
GROUP BY DATE(created_at);

CREATE OR REPLACE VIEW v_user_activity AS
SELECT 
    u.id,
    u.username,
    u.credit_score,
    u.seller_rating,
    u.total_sales,
    u.total_purchases,
    COUNT(DISTINCT i.id) AS active_items,
    COUNT(DISTINCT m.id) AS message_count,
    MAX(u.last_login_at) AS last_active
FROM users u
LEFT JOIN items i ON i.seller_id = u.id AND i.status = 'available'
LEFT JOIN messages m ON m.sender_id = u.id
WHERE u.is_active = TRUE AND u.is_banned = FALSE
GROUP BY u.id, u.username, u.credit_score, u.seller_rating, u.total_sales, u.total_purchases;

-- ============================================
-- 7. 扩展关联表
-- ============================================

CREATE TABLE IF NOT EXISTS user_follows (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    follower_id BIGINT NOT NULL,
    following_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    UNIQUE KEY uk_follower_following (follower_id, following_id),
    INDEX idx_follower (follower_id),
    INDEX idx_following (following_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (following_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户关注表';

CREATE TABLE IF NOT EXISTS item_view_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    view_duration INT DEFAULT 0,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_user (user_id),
    INDEX idx_item (item_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品浏览历史表';

CREATE TABLE IF NOT EXISTS user_addresses (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    address_type ENUM('dormitory', 'home', 'other') DEFAULT 'dormitory',
    building VARCHAR(50),
    room VARCHAR(20),
    detail_address VARCHAR(200),
    contact_name VARCHAR(50),
    contact_phone VARCHAR(20),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_user (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户地址表';

CREATE TABLE IF NOT EXISTS item_price_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    item_id BIGINT NOT NULL,
    old_price DECIMAL(10, 2),
    new_price DECIMAL(10, 2) NOT NULL,
    change_reason VARCHAR(200),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_item (item_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品价格历史表';


CREATE TABLE IF NOT EXISTS message_attachments (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    message_id BIGINT NOT NULL,
    file_type ENUM('image', 'video', 'document', 'other') DEFAULT 'image',
    file_url VARCHAR(500) NOT NULL,
    file_name VARCHAR(200),
    file_size BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息附件表';


CREATE TABLE IF NOT EXISTS transaction_review_images (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    transaction_id BIGINT NOT NULL,
    reviewer_type ENUM('buyer', 'seller') NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易评价图片表';

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    type ENUM('system', 'transaction', 'message', 'comment', 'follow', 'like') NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    related_id BIGINT,
    related_type VARCHAR(50),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_user (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统通知表';

CREATE TABLE IF NOT EXISTS search_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT,
    keyword VARCHAR(200) NOT NULL,
    result_count INT DEFAULT 0,
    clicked_item_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (clicked_item_id) REFERENCES items(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='搜索历史表';


CREATE TABLE IF NOT EXISTS sync_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_type ENUM('full_sync', 'incremental_sync', 'conflict_resolution') NOT NULL,
    source_db VARCHAR(50) NOT NULL,
    target_db VARCHAR(50) NOT NULL,
    table_name VARCHAR(100),
    status ENUM('pending', 'running', 'completed', 'failed') DEFAULT 'pending',
    total_records INT DEFAULT 0,
    synced_records INT DEFAULT 0,
    failed_records INT DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据库同步任务表';

CREATE TABLE IF NOT EXISTS performance_metrics (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    metric_type ENUM('query_time', 'query_time_avg', 'connection_pool', 'connections', 'sync_latency', 'error_rate') NOT NULL,
    db_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(10, 2) NOT NULL,
    threshold_value DECIMAL(10, 2),
    is_alert BOOLEAN DEFAULT FALSE,
    details JSON,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_type (metric_type),
    INDEX idx_db (db_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='性能监控表';

-- ============================================
-- Sync相关表
-- ============================================

-- sync_configs table
CREATE TABLE IF NOT EXISTS sync_configs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source VARCHAR(64) NOT NULL,
    target VARCHAR(64) NOT NULL,
    mode VARCHAR(32) NOT NULL DEFAULT 'realtime',
    interval_seconds INT NOT NULL DEFAULT 300,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    last_run_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- sync_logs table
CREATE TABLE IF NOT EXISTS sync_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    config_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    stats JSON NOT NULL DEFAULT ('{}'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    FOREIGN KEY (config_id) REFERENCES sync_configs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- sync_worker_state table (consumer cursor persisted in DB)
CREATE TABLE IF NOT EXISTS sync_worker_state (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    worker_name VARCHAR(128) NOT NULL UNIQUE,
    last_event_id BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conflict_records table
CREATE TABLE IF NOT EXISTS conflict_records (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    table_name VARCHAR(128) NOT NULL,
    record_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    target VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    payload JSON NULL,
    resolved TINYINT(1) NOT NULL DEFAULT 0,
    resolved_by BIGINT NULL,
    resolved_at TIMESTAMP NULL,
    resolution_note VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0,
    INDEX idx_table_record (table_name, record_id),
    FOREIGN KEY (resolved_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- daily_stats table
CREATE TABLE IF NOT EXISTS daily_stats (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    stat_date DATE NOT NULL UNIQUE,
    sync_success_count INT NOT NULL DEFAULT 0,
    sync_conflict_count INT NOT NULL DEFAULT 0,
    ai_request_count INT NOT NULL DEFAULT 0,
    inventory_changes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sync_version INT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 完成
SELECT 'MySQL/MariaDB schema created successfully!' AS message;

-- 插入默认角色
INSERT IGNORE INTO roles (name, description) VALUES
('admin', '系统管理员'),
('moderator', '内容审核员'),
('user', '普通用户'),
('seller', '认证卖家');

-- 插入默认权限
INSERT IGNORE INTO permissions (name, resource, action, description) VALUES
('user:read', 'user', 'read', '查看用户信息'),
('user:write', 'user', 'write', '修改用户信息'),
('user:delete', 'user', 'delete', '删除用户'),
('item:read', 'item', 'read', '查看商品'),
('item:write', 'item', 'write', '发布/修改商品'),
('item:delete', 'item', 'delete', '删除商品'),
('order:read', 'order', 'read', '查看订单'),
('order:write', 'order', 'write', '创建/修改订单'),
('admin:access', 'admin', 'access', '访问管理后台'),
('report:handle', 'report', 'handle', '处理举报');

-- 角色权限关联
INSERT IGNORE INTO role_permissions (role_id, permission_id) VALUES
-- admin 拥有所有权限
(1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10),
-- moderator 拥有审核权限
(2, 1), (2, 4), (2, 6), (2, 7), (2, 9), (2, 10),
-- user 拥有基本权限
(3, 1), (3, 4), (3, 5), (3, 7), (3, 8),
-- seller 拥有卖家权限
(4, 1), (4, 4), (4, 5), (4, 6), (4, 7), (4, 8);

-- ============================================
-- 同步配置/日志/统计/性能指标属于运行态数据，不在初始化阶段插入“示例/模拟”记录。

-- ============================================
-- 管理员账户 (密码: 041210)
-- ============================================

-- 初始化RBAC数据
INSERT IGNORE INTO roles (name, description, sync_version) VALUES
('admin', '系统管理员', 1),
('moderator', '内容审核员', 1),
('user', '普通用户', 1),
('seller', '认证卖家', 1);

INSERT IGNORE INTO permissions (name, resource, action, description, sync_version) VALUES
('user:read', 'user', 'read', '查看用户信息', 1),
('user:write', 'user', 'write', '修改用户信息', 1),
('user:delete', 'user', 'delete', '删除用户', 1),
('item:read', 'item', 'read', '查看商品', 1),
('item:write', 'item', 'write', '发布/修改商品', 1),
('item:delete', 'item', 'delete', '删除商品', 1),
('order:read', 'order', 'read', '查看订单', 1),
('order:write', 'order', 'write', '创建/修改订单', 1),
('admin:access', 'admin', 'access', '访问管理后台', 1),
('report:handle', 'report', 'handle', '处理举报', 1);

INSERT IGNORE INTO role_permissions (role_id, permission_id, sync_version) VALUES
-- admin 拥有所有权限
(1, 1, 1), (1, 2, 1), (1, 3, 1), (1, 4, 1), (1, 5, 1), (1, 6, 1), (1, 7, 1), (1, 8, 1), (1, 9, 1), (1, 10, 1),
-- moderator 拥有审核权限
(2, 1, 1), (2, 4, 1), (2, 6, 1), (2, 7, 1), (2, 9, 1), (2, 10, 1),
-- user 拥有基本权限
(3, 1, 1), (3, 4, 1), (3, 5, 1), (3, 7, 1), (3, 8, 1),
-- seller 拥有卖家权限
(4, 1, 1), (4, 4, 1), (4, 5, 1), (4, 6, 1), (4, 7, 1), (4, 8, 1);

INSERT IGNORE INTO users (id, username, email, password_hash, is_active, is_verified, credit_score) VALUES
(9999, 'admin', 'admin@campus.edu', '$2b$12$KLysJ85PhtqHTQGptnrr6.c1yOdB51s1j65u8dsOPtiVssLJKi/De', 1, 1, 100);

-- 为管理员分配admin角色
INSERT IGNORE INTO user_roles (user_id, role_id) 
SELECT 9999, id FROM roles WHERE name = 'admin';

-- 性能指标属于运行态数据，不在初始化阶段插入“示例/模拟”记录。

SET FOREIGN_KEY_CHECKS = 1;

SELECT 'MySQL init completed (no simulated runtime data seeded).' AS message;
