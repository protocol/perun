using System.Data.SqlClient;

public class UserRepo
{
    public SqlDataReader Find(SqlConnection conn, string name)
    {
        var cmd = new SqlCommand("SELECT * FROM users WHERE name = '" + name + "'", conn);
        return cmd.ExecuteReader();
    }
}
