package com.backendtemplate;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = "spring.profiles.active=no-db")
class TemplateApplicationTests {

	@Test
	void contextLoads() {
	}

}
