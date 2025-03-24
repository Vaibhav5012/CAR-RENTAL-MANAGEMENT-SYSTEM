-- Active: 1742816071690@@127.0.0.1@3306@car_rental
CREATE TABLE Customers (
    customer_id INT PRIMARY KEY AUTO_INCREMENT,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100),
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(15),
    address VARCHAR(255)
);

DROP TABLE admins;
CREATE TABLE Admins (
    admin_id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

INSERT INTO Admins (username, password)
VALUES ('Admin1', SHA2('admin@12', 256));

INSERT INTO Admins (username, password)
VALUES ('Admin2', SHA2('admin@12', 256));

CREATE TABLE Cars (
    car_id INT PRIMARY KEY AUTO_INCREMENT,
    model VARCHAR(50),
    make VARCHAR(50),
    year INT,
    registration_number VARCHAR(20),
    status ENUM('Available', 'Rented', 'Under Maintenance') DEFAULT 'Available',
    price_per_day DECIMAL(10, 2)
);

CREATE TABLE Rentals (
    rental_id INT PRIMARY KEY AUTO_INCREMENT,
    customer_id INT,
    car_id INT,
    start_date DATE,
    end_date DATE,
    total_cost DECIMAL(10, 2),
    status ENUM('Ongoing', 'Completed', 'Cancelled') DEFAULT 'Ongoing',
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (car_id) REFERENCES Cars(car_id) ON DELETE CASCADE
);

CREATE TABLE Payments (
    payment_id INT PRIMARY KEY AUTO_INCREMENT,
    rental_id INT,
    amount DECIMAL(10, 2),
    payment_date DATE,
    payment_method VARCHAR(50),
    FOREIGN KEY (rental_id) REFERENCES Rentals(rental_id) ON DELETE CASCADE
);


ALTER TABLE Customers ADD COLUMN password VARCHAR(256) NOT NULL;
ALTER TABLE Cars ADD UNIQUE (registration_number);


-- Insert initial data
INSERT INTO Cars (model, make, year, registration_number, status, price_per_day)
VALUES ('Civic', 'Honda', 2023, 'ABC123', 'Available', 50.00);

INSERT INTO Cars (model, make, year, registration_number, status, price_per_day)
VALUES ('Corolla', 'Toyota', 2022, 'DEF456', 'Available', 45.00);

INSERT INTO Customers (first_name, last_name, email, password, phone, address)
VALUES ('John', 'Doe', 'john.doe@example.com', SHA2('john@12', 256), '1234567890', '123 Main St');

INSERT INTO Rentals (customer_id, car_id, start_date, end_date, total_cost, status)
VALUES (1, 1, '2025-03-01', '2025-03-05', 200.00, 'Ongoing');

INSERT INTO Payments (rental_id, amount, payment_date, payment_method)
VALUES (1, 200.00, '2025-03-05', 'Credit Card');

-- Update rental status
UPDATE Rentals
SET status = 'Completed'
WHERE rental_id = 1;

-- Select available cars
SELECT * FROM Cars WHERE status = 'Available';

-- Let me know if you face any other issues or want me to add more data! 🚀

SELECT * FROM Cars;
SELECT * FROM Customers;
SELECT * FROM Rentals;
SELECT * FROM Payments;

SELECT * FROM admins;