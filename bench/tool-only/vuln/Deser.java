import java.io.InputStream;
import java.io.ObjectInputStream;

public class Deser {
    public static Object read(InputStream in) throws Exception {
        ObjectInputStream ois = new ObjectInputStream(in);
        return ois.readObject();
    }
}
