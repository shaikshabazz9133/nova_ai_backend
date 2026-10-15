
from security import hash_password, verify_password

password = "MySecretPassword123"

# Create a secure password hash
hashed_password = hash_password(password)

print("Original password:", password)
print("Hashed password:", hashed_password)

# Verify the correct password
print("Correct password:", verify_password(
    password, hashed_password
))

# Verify an incorrect password
print("Wrong password:", verify_password(
    "WrongPassword123", hashed_password
))
