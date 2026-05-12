import { createAuthClient } from "better-auth/react"
import { customSessionClient } from "better-auth/client/plugins";
import type { auth } from "@/lib/auth";

export const authClient =  createAuthClient({
    plugins: [customSessionClient<typeof auth>()],
    session: {
        refetchOnWindowFocus: false, // Disable automatic refetch when window gains focus
    },
    fetchOptions: {
        onError(context) {
            console.error(context.error);
        },
    }
})

 
export const { useSession } = authClient;

 
export const signInSocial = async (provider:string) => {
    const data = await authClient.signIn.social({
        provider: provider,
        callbackURL: '/dashboard'
    })
}

export const signInEmail = async (email:string, password:string) => {
    const data = await authClient.signIn.email({
        email,
        password,
        callbackURL: '/'
    })
}

export const signUpEmail = async (name: string, email: string, password: string) => {
    const data = await authClient.signUp.email({
        email,
        password,
        name,
        callbackURL: '/'
    })
}
