from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('token_blacklist', '0007_auto_20171017_2214'),
        ('API', '0001_initial'),  # Adjust based on your last API migration
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DECLARE @constraint_name NVARCHAR(256)
            SELECT @constraint_name = name 
            FROM sys.key_constraints 
            WHERE parent_object_id = OBJECT_ID('token_blacklist_blacklistedtoken') 
            AND type = 'UQ'
            
            IF @constraint_name IS NOT NULL
                EXEC('ALTER TABLE token_blacklist_blacklistedtoken DROP CONSTRAINT ' + @constraint_name)
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]