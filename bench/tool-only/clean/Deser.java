import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputStream;
import java.io.ObjectStreamClass;
import java.util.Set;

public class Deser extends ObjectInputStream {
    private static final Set<String> ALLOWED = Set.of("java.lang.String", "java.lang.Integer", "java.lang.Number");

    public Deser(InputStream in) throws IOException {
        super(in);
    }

    @Override
    protected Class<?> resolveClass(ObjectStreamClass desc) throws IOException, ClassNotFoundException {
        if (!ALLOWED.contains(desc.getName())) {
            throw new java.io.InvalidClassException("class not allowed", desc.getName());
        }
        return super.resolveClass(desc);
    }
}
