package example.library;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new BearerInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**", "/api/catalog/export/**");
        registry.addInterceptor(new SessionInterceptor()).addPathPatterns("/web/**");
    }
}
