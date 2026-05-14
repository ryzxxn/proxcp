import { betterAuth } from "better-auth";
import { customSession } from "better-auth/plugins";
import Database from "better-sqlite3";
 
export const auth = betterAuth({
    database: new Database("./data/auth.db"),

    plugins: [
        customSession(async ({ user, session }) => {
            return {
                user: {
                    ...user,
                },
                session,
            };
        }),
    ],

    emailAndPassword: {
        enabled: true,
    },
})
