package com.backendtemplate;

import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.context.TestComponent;
import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

public class ShutdownWorker {
    public static void main(String[] args) {
        var app = new SpringApplicationBuilder(TemplateApplication.class, Routes.class)
                .run("--server.port=0", "--spring.datasource.url=" + args[0]);
        System.out.println("SERVER_PORT:" + ((WebServerApplicationContext) app).getWebServer().getPort());
        System.out.flush();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class Routes {
        @Bean
        SlowEndpoint slowEndpoint() {
            return new SlowEndpoint();
        }
    }

    @RestController
    @TestComponent
    static class SlowEndpoint {
        @GetMapping("/slow")
        String slow() throws InterruptedException {
            System.out.println("REQUEST_ACTIVE");
            System.out.flush();
            Thread.sleep(600);
            return "finished";
        }
    }
}
